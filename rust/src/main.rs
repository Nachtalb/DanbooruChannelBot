mod config;
mod danbooru;
mod format;
mod settings;

use std::{
    collections::VecDeque,
    path::PathBuf,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, AtomicU64, Ordering::SeqCst},
    },
    time::Duration,
};

use chrono::Utc;
use serde_json::{Value, json};
use teloxide::{
    prelude::*,
    types::{InlineKeyboardButton, InlineKeyboardMarkup, InputFile, ParseMode},
    update_listeners::webhooks,
    utils::html::escape,
};
use tokio::sync::Notify;

use crate::{
    config::Config,
    danbooru::{Danbooru, Kind, Media, Post},
    format::{Mode, Outgoing},
    settings::Settings,
};

pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;

struct App {
    s: Settings,
    tg: Bot,
    db: Danbooru,
    subs: Mutex<serde_json::Map<String, Value>>,
    /// Last 100 sent post ids (LAST_100_TRACK)
    tracker: Mutex<VecDeque<u64>>,
    last_post: AtomicU64,
    job: AtomicBool,
    refreshing: AtomicBool,
    manual: AtomicBool,
    cancel: AtomicBool,
    wake: Notify,
}

impl App {
    fn path(&self, name: &str) -> PathBuf {
        self.s.config_folder.join(name)
    }

    fn save_subs(&self, subs: &serde_json::Map<String, Value>) {
        let text = serde_json::to_string_pretty(subs).unwrap();
        if let Err(e) = std::fs::write(self.path("sub_config.json"), text) {
            log::error!("Could not save sub_config.json: {e}");
        }
    }

    /// Run `f` on the chats config and persist it. The main chat has no config.
    fn edit_config(&self, chat: i64, f: impl FnOnce(&mut Config) -> String) -> String {
        if chat == self.s.chat_id {
            return "The main chat is configured via environment variables".into();
        }
        let mut subs = self.subs.lock().unwrap();
        let cfg = subs.entry(chat.to_string()).or_insert_with(config::default_config);
        if !cfg.is_object() {
            *cfg = config::default_config();
        }
        let reply = f(cfg.as_object_mut().unwrap());
        self.save_subs(&subs);
        reply
    }

    async fn last_post_id(&self) -> Result<u64> {
        match self.last_post.load(SeqCst) {
            0 => {}
            id => return Ok(id),
        }
        let id = match std::fs::read_to_string(self.path("last_post.txt")) {
            Ok(text) => text.trim().parse()?,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => self.latest_post_id().await?,
            Err(e) => return Err(e.into()),
        };
        self.set_last_post_id(id);
        Ok(id)
    }

    fn set_last_post_id(&self, id: u64) {
        self.last_post.store(id, SeqCst);
        if let Err(e) = std::fs::write(self.path("last_post.txt"), id.to_string()) {
            log::error!("Could not save last_post.txt: {e}");
        }
    }

    async fn latest_post_id(&self) -> Result<u64> {
        let posts = self.db.posts(1, "").await?;
        Ok(posts.first().and_then(|p| p["id"].as_u64()).ok_or("could not get the latest post")?)
    }

    fn parse(value: Value) -> Option<Post> {
        serde_json::from_value(value).map_err(|e| log::warn!("Skip restricted post: {e}")).ok()
    }

    async fn get_posts(&self) -> Result<Vec<Post>> {
        let mut posts = Vec::new();
        if !self.s.search_tags.is_empty() {
            let raw = self.db.posts(100, &self.s.search_tags).await?;
            let last = if self.s.last_100_track { 0 } else { self.last_post_id().await? };
            let tracker = self.tracker.lock().unwrap().clone();
            for post in raw.into_iter().rev().filter_map(Self::parse) {
                let seen = if self.s.last_100_track { tracker.contains(&post.id) } else { post.id <= last };
                if !seen && format::is_ok(&post, &self.s.post_tag_filter) {
                    posts.push(post);
                }
            }
            return Ok(posts);
        }

        let latest = self.latest_post_id().await?;
        let last = self.last_post_id().await?;
        if latest <= last {
            return Ok(posts);
        }
        let mut batch = self.db.posts((latest - last).min(200), "").await?;
        for id in last + 1..=latest {
            let value = match batch.iter().position(|p| p["id"].as_u64() == Some(id)) {
                Some(i) => batch.swap_remove(i),
                None => match self.db.post(id).await {
                    Ok(value) => value,
                    Err(e) => {
                        log::warn!("Exception during downloading info for post {id}: {e}");
                        continue;
                    }
                },
            };
            let Some(post) = Self::parse(value) else { continue };
            if (Utc::now().fixed_offset() - post.created_at).num_seconds() < self.s.grace_period {
                // None of the following posts are older
                break;
            }
            if format::is_ok(&post, &self.s.post_tag_filter) {
                posts.push(post);
            }
        }
        Ok(posts)
    }

    /// Returns false if a refresh is already running
    async fn refresh(&self, manual: bool) -> bool {
        if self.refreshing.swap(true, SeqCst) {
            log::info!("Refresh already running");
            return false;
        }
        self.manual.store(manual, SeqCst);
        self.cancel.store(false, SeqCst);
        log::info!("Start refresh");
        if let Err(e) = self.send_posts().await {
            log::error!("Refresh failed: {e}");
        }
        self.manual.store(false, SeqCst);
        self.refreshing.store(false, SeqCst);
        log::info!("Finished refresh");
        true
    }

    async fn send_posts(&self) -> Result<()> {
        // Same pace as the old message queue: 2 posts per 6 seconds
        let mut pace = tokio::time::interval(Duration::from_secs(3));
        for post in self.get_posts().await? {
            if self.cancel.load(SeqCst) {
                log::info!("Early termination");
                break;
            }
            if !self.job.load(SeqCst) && !self.manual.load(SeqCst) {
                log::info!("Scheduled task was stopped while refreshing");
                break;
            }
            pace.tick().await;
            if let Err(e) = self.send_post(&post).await {
                log::error!("Could not send post {}: {e}", post.id);
            }
        }
        Ok(())
    }

    async fn send_post(&self, post: &Post) -> Result<()> {
        log::info!("┏ {}: Preparing", post.id);
        let media = danbooru::prepare(&self.db, post).await?;

        let subs = self.subs.lock().unwrap().clone();
        let chats = subs.iter().filter_map(|(chat, cfg)| Some((chat.parse().ok()?, cfg.as_object())));
        for (chat, cfg) in std::iter::once((self.s.chat_id, None)).chain(chats) {
            let Some(out) = format::create_post(post, cfg, &self.s) else { continue };
            log::info!("┃ Send to {chat}");
            if let Err(e) = self.send(ChatId(chat), &out, &media).await {
                log::error!("┃ Sending to {chat} failed: {e}");
            }
        }
        log::info!("┗━━");

        self.set_last_post_id(post.id);
        if self.s.last_100_track {
            let mut tracker = self.tracker.lock().unwrap();
            tracker.push_back(post.id);
            while tracker.len() > 100 {
                tracker.pop_front();
            }
            let text = tracker.iter().map(u64::to_string).collect::<Vec<_>>().join(" ");
            std::fs::write(self.path("tracker.txt"), text)?;
        }
        Ok(())
    }

    async fn send(&self, chat: ChatId, out: &Outgoing, media: &Media) -> Result<()> {
        let buttons = out.buttons.iter().map(|(text, url)| InlineKeyboardButton::url(text.clone(), url.clone()));
        let markup = InlineKeyboardMarkup::new([buttons.collect::<Vec<_>>()]);
        let file = |data: &Vec<u8>| InputFile::memory(data.clone()).file_name(media.name.clone());
        let caption = out.caption.clone();

        macro_rules! send {
            ($req:expr) => {{
                let req = $req.parse_mode(ParseMode::Html);
                match out.buttons.is_empty() {
                    true => req.await?,
                    false => req.reply_markup(markup).await?,
                };
            }};
        }

        let tg = &self.tg;
        let kind = if out.mode == Mode::Document { Kind::Document } else { media.kind };
        match (&out.mode, kind) {
            (Mode::Text, _) => send!(tg.send_message(chat, caption)),
            (_, Kind::Document) => send!(tg.send_document(chat, file(&media.data)).caption(caption)),
            (_, Kind::Photo) => {
                let data = media.photo.as_ref().unwrap_or(&media.data);
                send!(tg.send_photo(chat, file(data)).caption(caption))
            }
            (_, Kind::Animation) => {
                let mut req = tg.send_animation(chat, file(&media.data)).caption(caption);
                if let Some(d) = media.duration {
                    req = req.duration(d);
                }
                if let Some(thumb) = &media.thumb {
                    req = req.thumbnail(InputFile::memory(thumb.clone()));
                }
                send!(req)
            }
            (_, Kind::Video) => {
                let mut req = tg.send_video(chat, file(&media.data)).caption(caption).supports_streaming(true);
                if let Some(d) = media.duration {
                    req = req.duration(d);
                }
                send!(req)
            }
        }
        Ok(())
    }

    fn is_admin(&self, msg: &Message) -> bool {
        let name = msg.from.as_ref().and_then(|u| u.username.as_ref());
        name.is_some_and(|n| self.s.admins.contains(&n.to_lowercase()))
    }

    async fn handle(self: Arc<Self>, msg: Message) -> Result<()> {
        let Some(text) = msg.text() else { return Ok(()) };
        let chat = msg.chat.id;

        if text.eq_ignore_ascii_case("r") {
            self.tg.delete_message(chat, msg.id).await?;
            tokio::spawn(async move { self.refresh(true).await });
            return Ok(());
        }

        let Some(text) = text.strip_prefix('/') else { return Ok(()) };
        let mut args: Vec<String> = text.split_whitespace().map(String::from).collect();
        if args.is_empty() {
            return Ok(());
        }
        let cmd = args.remove(0).split('@').next().unwrap_or_default().to_lowercase();
        let admin = self.is_admin(&msg);

        let reply = match cmd.as_str() {
            "config" => self.edit_config(chat.0, |cfg| config::config_command(cfg, &args)),
            "sub" | "unsub" => self.edit_config(chat.0, |cfg| config::sub_command(cfg, &args, cmd == "sub")),
            "gsub" | "gunsub" => self.edit_config(chat.0, |cfg| config::group_command(cfg, &args, cmd == "gsub")),
            key if config::SAFE_KEYS.contains(&key) || config::UNSAFE_KEYS.contains(&key) => {
                args.insert(0, cmd.clone());
                self.edit_config(chat.0, |cfg| config::config_command(cfg, &args))
            }
            "id" => {
                let user = msg.from.as_ref().map_or("-".into(), |u| match &u.username {
                    Some(name) => format!("@{name}"),
                    None => u.full_name(),
                });
                let info = json!({"chat_id": chat.0, "message_id": msg.id.0, "user": user});
                format!("<code>{}</code>", escape(&serde_json::to_string_pretty(&info)?))
            }
            _ if !admin => return Ok(()),
            "refresh" if self.refreshing.load(SeqCst) => "Refresh already running".into(),
            "refresh" => {
                let app = self.clone();
                tokio::spawn(async move {
                    if app.refresh(true).await {
                        let _ = app.tg.send_message(chat, "Finished refresh").await;
                    }
                });
                "Start refresh".into()
            }
            "start" if self.job.load(SeqCst) => "Job already exists".into(),
            "start" => {
                self.job.store(true, SeqCst);
                self.wake.notify_one();
                "Starting job".into()
            }
            "stop" if self.manual.load(SeqCst) => {
                self.cancel.store(true, SeqCst);
                "Refresh was stopped".into()
            }
            "stop" if !self.job.load(SeqCst) => "Job already removed".into(),
            "stop" => {
                self.job.store(false, SeqCst);
                "Job scheduled for removal".into()
            }
            "cancel" if !self.refreshing.load(SeqCst) => "No running refresh".into(),
            "cancel" => {
                self.cancel.store(true, SeqCst);
                "Current refresh was cancelled".into()
            }
            "chat" => {
                let info = self.tg.get_chat(ChatId(self.s.chat_id)).await?;
                let name = escape(info.title().or(info.username()).unwrap_or("-"));
                format!("Chat: {name} -> <code>{}</code>", self.s.chat_id)
            }
            _ => return Ok(()),
        };
        self.tg.send_message(chat, reply).parse_mode(ParseMode::Html).await?;
        Ok(())
    }
}

fn load_subs(path: &PathBuf) -> serde_json::Map<String, Value> {
    let text = std::fs::read_to_string(path).unwrap_or_default();
    match text.trim() {
        "" => Default::default(),
        text => serde_json::from_str(text).expect("sub_config.json is not a valid json object"),
    }
}

#[tokio::main]
async fn main() {
    let _ = dotenvy::dotenv();
    let debug = std::env::var("DEBUG").is_ok_and(|v| matches!(v.to_lowercase().as_str(), "1" | "true" | "yes"));
    env_logger::Builder::new()
        .filter_level(if debug { log::LevelFilter::Debug } else { log::LevelFilter::Warn })
        .parse_default_env()
        .init();

    let mut s = Settings::from_env();
    let tg = Bot::new(&s.token);
    let db = Danbooru::new(s.danbooru_url.clone(), s.danbooru_user.take(), s.danbooru_api.take());
    let tracker = std::fs::read_to_string(s.config_folder.join("tracker.txt")).unwrap_or_default();
    let webhook = s.webhook.take();

    let app = Arc::new(App {
        subs: Mutex::new(load_subs(&s.config_folder.join("sub_config.json"))),
        tracker: Mutex::new(tracker.split_whitespace().filter_map(|id| id.parse().ok()).collect()),
        last_post: AtomicU64::new(0),
        job: AtomicBool::new(s.auto_start),
        refreshing: AtomicBool::new(false),
        manual: AtomicBool::new(false),
        cancel: AtomicBool::new(false),
        wake: Notify::new(),
        s,
        tg: tg.clone(),
        db,
    });

    let me = tg.get_me().await.expect("could not reach telegram, is TELEGRAM_API_TOKEN correct?");
    log::warn!("Start {} as: @{}", if webhook.is_some() { "webhook" } else { "polling" }, me.username());

    let scheduler = app.clone();
    tokio::spawn(async move {
        let interval = Duration::from_secs(scheduler.s.reload_interval * 60);
        loop {
            if scheduler.job.load(SeqCst) {
                scheduler.refresh(false).await;
            }
            tokio::select! {
                _ = tokio::time::sleep(interval) => {}
                _ = scheduler.wake.notified() => {}
            }
        }
    });

    let handler = dptree::entry()
        .branch(Update::filter_message().endpoint(App::handle))
        .branch(Update::filter_channel_post().endpoint(App::handle));
    let mut dispatcher = Dispatcher::builder(tg.clone(), handler)
        .dependencies(dptree::deps![app])
        .error_handler(LoggingErrorHandler::new())
        .enable_ctrlc_handler()
        .build();

    match webhook {
        Some(options) => {
            let listener = webhooks::axum(tg, options).await.expect("could not set up the webhook");
            let errors = LoggingErrorHandler::with_custom_text("Update listener error");
            dispatcher.dispatch_with_listener(listener, errors).await
        }
        None => dispatcher.dispatch().await,
    }
}
