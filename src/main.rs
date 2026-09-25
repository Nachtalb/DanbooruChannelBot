mod config;
mod danbooru;
mod format;
mod settings;

use std::{
    collections::{HashMap, VecDeque},
    path::PathBuf,
    sync::{
        Arc, Mutex, OnceLock, RwLock,
        atomic::{AtomicBool, AtomicU64, Ordering::SeqCst},
    },
    time::Duration,
};

use chrono::Utc;
use serde_json::{Map, Value, json};
use teloxide::{
    ApiError, RequestError,
    dispatching::ShutdownToken,
    prelude::*,
    types::{FileId, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, ParseMode},
    update_listeners::webhooks,
    utils::html::escape,
};
use tokio::sync::Notify;

use crate::{
    config::Config,
    danbooru::{Batch, Danbooru, Kind, Media, PAGE_LIMIT, Post},
    format::{Mode, Outgoing},
    settings::Settings,
};

pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;

const RESTARTED_ARG: &str = "--restarted-in=";

struct App {
    settings: RwLock<Arc<Settings>>,
    tg: Bot,
    username: String,
    db: Danbooru,
    subs: Mutex<Map<String, Value>>,
    /// Last 100 sent post ids (LAST_100_TRACK)
    tracker: Mutex<VecDeque<u64>>,
    last_post: AtomicU64,
    job: AtomicBool,
    refreshing: AtomicBool,
    manual: AtomicBool,
    cancel: AtomicBool,
    wake: Notify,
    shutdown: OnceLock<ShutdownToken>,
    restart_in: Mutex<Option<ChatId>>,
}

impl App {
    fn s(&self) -> Arc<Settings> {
        self.settings.read().unwrap().clone()
    }

    fn update_settings(&self, f: impl FnOnce(&mut Settings) -> std::result::Result<(), String>) -> Option<String> {
        let mut settings = self.settings.write().unwrap();
        let mut new = (**settings).clone();
        f(&mut new).err().or_else(|| {
            *settings = Arc::new(new);
            None
        })
    }

    fn path(&self, name: &str) -> PathBuf {
        self.s().config_folder.join(name)
    }

    fn save_subs(&self, subs: &Map<String, Value>) {
        let text = serde_json::to_string_pretty(subs).unwrap();
        if let Err(e) = std::fs::write(self.path("sub_config.json"), text) {
            log::error!("Could not save sub_config.json: {e}");
        }
    }

    /// Run `f` on the chats config and persist it. The main chat has no config.
    fn edit_config(&self, chat: i64, f: impl FnOnce(&mut Config) -> String) -> String {
        if chat == self.s().chat_id {
            return "The main chat is configured via the environment variables".into();
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

    /// Groups become supergroups with a new id
    fn migrate(&self, old: ChatId, new: ChatId) {
        log::warn!("Chat {old} migrated to {new}");
        if old.0 == self.s().chat_id {
            log::warn!("Update CHAT_ID to {new}");
            self.update_settings(|s| {
                s.chat_id = new.0;
                Ok(())
            });
        }
        let mut subs = self.subs.lock().unwrap();
        if let Some(cfg) = subs.remove(&old.to_string()) {
            subs.insert(new.to_string(), cfg);
            self.save_subs(&subs);
        }
    }

    async fn last_post_id(&self) -> Result<u64> {
        if let id @ 1.. = self.last_post.load(SeqCst) {
            return Ok(id);
        }
        let id = match std::fs::read_to_string(self.path("last_post.txt")) {
            Ok(text) => text.trim().parse()?,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                let latest = self.db.posts("", 1, None).await?;
                latest
                    .first()
                    .and_then(|p| p["id"].as_u64())
                    .ok_or("could not get the latest post")?
            }
            Err(e) => return Err(e.into()),
        };
        self.set_last_post_id(id);
        Ok(id)
    }

    fn set_last_post_id(&self, id: u64) {
        if self.last_post.fetch_max(id, SeqCst) >= id {
            return;
        }
        if let Err(e) = std::fs::write(self.path("last_post.txt"), id.to_string()) {
            log::error!("Could not save last_post.txt: {e}");
        }
    }

    async fn get_posts(&self) -> Result<Batch> {
        let s = self.s();
        let last = self.last_post_id().await?;
        let track = s.last_100_track && !s.search_tags.is_empty();
        let raw = match track {
            true => self.db.posts(&s.search_tags, 100, None).await?,
            false => self.db.posts(&s.search_tags, PAGE_LIMIT, Some(last)).await?,
        };
        let tracker = self.tracker.lock().unwrap().clone();
        let seen = |id| if track { tracker.contains(&id) } else { id <= last };
        let ok = |post: &Post| format::is_ok(post, &s.post_tag_filter);
        Ok(danbooru::select(
            raw,
            last,
            seen,
            s.grace_period,
            ok,
            Utc::now().fixed_offset(),
        ))
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

    fn stopped(&self) -> bool {
        self.cancel.load(SeqCst) || (!self.job.load(SeqCst) && !self.manual.load(SeqCst))
    }

    async fn send_posts(&self) -> Result<()> {
        let batch = self.get_posts().await?;
        // At most 20 messages per minute to the same chat
        let mut pace = tokio::time::interval(Duration::from_secs(3));
        for post in &batch.posts {
            if self.stopped() {
                log::info!("Refresh stopped");
                return Ok(());
            }
            pace.tick().await;
            if let Err(e) = self.send_post(post).await {
                log::error!("Could not send post {}: {e}", post.id);
            }
        }
        if !self.stopped() {
            self.set_last_post_id(batch.scanned);
        }
        Ok(())
    }

    async fn send_post(&self, post: &Post) -> Result<()> {
        log::info!("┏ {}: Preparing", post.id);
        let media = danbooru::prepare(&self.db, post).await?;
        if media.is_none() {
            log::info!("┃ Too big for Telegram, sending as text");
        }
        let s = self.s();
        // Upload each file once, then reuse it by its Telegram file id
        let mut uploaded = HashMap::new();

        let subs = self.subs.lock().unwrap().clone();
        let chats = subs
            .iter()
            .filter_map(|(chat, cfg)| Some((chat.parse().ok()?, cfg.as_object())));
        for (chat, cfg) in std::iter::once((s.chat_id, None)).chain(chats) {
            let Some(out) = format::create_post(post, cfg, &s) else {
                continue;
            };
            log::info!("┃ Send to {chat}");
            if let Err(e) = self.send(ChatId(chat), post, &out, media.as_ref(), &mut uploaded).await {
                log::error!("┃ Sending to {chat} failed: {e}");
            }
        }
        log::info!("┗━━");

        self.set_last_post_id(post.id);
        if s.last_100_track {
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

    /// Sends the post, waits on flood limits, follows chat migrations and falls back to a
    /// text message with a link if there is no file or Telegram refuses it.
    async fn send(
        &self,
        mut chat: ChatId,
        post: &Post,
        out: &Outgoing,
        media: Option<&Media>,
        uploaded: &mut HashMap<Kind, FileId>,
    ) -> Result<()> {
        let mut media = media.filter(|_| out.mode != Mode::Text);
        for _ in 0..5 {
            let result = match media {
                None => self.send_text(chat, post, out).await,
                Some(media) => self.send_media(chat, out, media, uploaded).await,
            };
            match result {
                Ok(()) => return Ok(()),
                Err(RequestError::RetryAfter(wait)) => tokio::time::sleep(wait.duration()).await,
                Err(RequestError::MigrateToChatId(new)) => {
                    self.migrate(chat, new);
                    chat = new;
                }
                Err(RequestError::Api(e)) if chat.0 != self.s().chat_id && chat_gone(&e) => {
                    log::warn!("┃ Removing the subscription of {chat}: {e}");
                    let mut subs = self.subs.lock().unwrap();
                    subs.remove(&chat.to_string());
                    self.save_subs(&subs);
                    return Ok(());
                }
                Err(e) if media.is_some() => {
                    log::warn!("┃ Sending file failed ({e}), sending as text");
                    media = None;
                }
                Err(e) => return Err(e.into()),
            }
        }
        Err("gave up after too many retries".into())
    }

    fn markup(out: &Outgoing) -> Option<InlineKeyboardMarkup> {
        let buttons = out
            .buttons
            .iter()
            .map(|(text, url)| InlineKeyboardButton::url(text.clone(), url.clone()));
        (!out.buttons.is_empty()).then(|| InlineKeyboardMarkup::new([buttons.collect::<Vec<_>>()]))
    }

    async fn send_text(&self, chat: ChatId, post: &Post, out: &Outgoing) -> std::result::Result<(), RequestError> {
        let mut text = out.caption.clone();
        if out.mode != Mode::Text {
            // Link the file so Telegram shows a preview of it
            text += &format!("\n<a href=\"{}\">{}</a>", escape(post.nice_file_url()), post.id);
        }
        let mut req = self.tg.send_message(chat, text).parse_mode(ParseMode::Html);
        if let Some(markup) = Self::markup(out) {
            req = req.reply_markup(markup);
        }
        req.await.map(drop)
    }

    async fn send_media(
        &self,
        chat: ChatId,
        out: &Outgoing,
        media: &Media,
        uploaded: &mut HashMap<Kind, FileId>,
    ) -> std::result::Result<(), RequestError> {
        let kind = if out.mode == Mode::Document {
            Kind::Document
        } else {
            media.kind
        };
        let file = match (uploaded.get(&kind), kind) {
            (Some(id), _) => InputFile::file_id(id.clone()),
            (None, Kind::Document) => InputFile::memory(media.original.clone()).file_name(media.original_name.clone()),
            (None, _) => InputFile::memory(media.data.clone()).file_name(media.name.clone()),
        };
        let (tg, caption, markup) = (&self.tg, out.caption.clone(), Self::markup(out));
        let thumb = media.thumb.clone().map(InputFile::memory);

        macro_rules! send {
            ($req:expr) => {{
                let mut req = $req.caption(caption).parse_mode(ParseMode::Html);
                if let Some(markup) = markup {
                    req = req.reply_markup(markup);
                }
                req.await?
            }};
        }

        let msg = match kind {
            Kind::Document => send!(tg.send_document(chat, file)),
            Kind::Photo => send!(tg.send_photo(chat, file)),
            Kind::Video => {
                let mut req = tg.send_video(chat, file).supports_streaming(true);
                (req.duration, req.width, req.height, req.thumbnail) =
                    (media.duration, media.width, media.height, thumb);
                send!(req)
            }
            Kind::Animation => {
                let mut req = tg.send_animation(chat, file);
                (req.duration, req.width, req.height, req.thumbnail) =
                    (media.duration, media.width, media.height, thumb);
                send!(req)
            }
        };
        let id = match kind {
            Kind::Photo => msg.photo().and_then(|sizes| sizes.last()).map(|p| &p.file.id),
            Kind::Video => msg.video().map(|v| &v.file.id),
            Kind::Animation => msg.animation().map(|a| &a.file.id),
            Kind::Document => msg.document().map(|d| &d.file.id),
        };
        if let Some(id) = id {
            uploaded.insert(kind, id.clone());
        }
        Ok(())
    }

    fn is_admin(&self, msg: &Message) -> bool {
        let name = msg.from.as_ref().and_then(|u| u.username.as_ref());
        name.is_some_and(|n| self.s().admins.contains(&n.to_lowercase()))
    }

    /// Bot admins everywhere, otherwise only group admins may change a groups config.
    /// Private chats and channels (only admins can post there) are always allowed.
    async fn can_configure(&self, msg: &Message) -> bool {
        if self.is_admin(msg) || msg.chat.is_private() || msg.chat.is_channel() {
            return true;
        }
        if msg.sender_chat.as_ref().is_some_and(|c| c.id == msg.chat.id) {
            return true; // anonymous group admin
        }
        let Some(user) = &msg.from else { return false };
        let member = self.tg.get_chat_member(msg.chat.id, user.id).await;
        member.is_ok_and(|m| m.is_privileged())
    }

    async fn handle(self: Arc<Self>, msg: Message) -> Result<()> {
        let Some(text) = msg.text() else {
            return Ok(());
        };
        let chat = msg.chat.id;
        let admin = self.is_admin(&msg);

        if text.eq_ignore_ascii_case("r") && admin {
            let _ = self.tg.delete_message(chat, msg.id).await;
            tokio::spawn(async move { self.refresh(true).await });
            return Ok(());
        }

        let Some(text) = text.strip_prefix('/') else {
            return Ok(());
        };
        let mut args: Vec<String> = text.split_whitespace().map(String::from).collect();
        if args.is_empty() {
            return Ok(());
        }
        let first = args.remove(0);
        let (cmd, target) = first.split_once('@').unwrap_or((&first, ""));
        if !target.is_empty() && !target.eq_ignore_ascii_case(&self.username) {
            return Ok(()); // command for another bot
        }
        let cmd = cmd.to_lowercase();

        let reply = match cmd.as_str() {
            "id" => {
                let user = msg.from.as_ref().map_or("-".into(), |u| match &u.username {
                    Some(name) => format!("@{name}"),
                    None => u.full_name(),
                });
                let info = json!({"chat_id": chat.0, "message_id": msg.id.0, "user": user});
                format!("<code>{}</code>", escape(&serde_json::to_string_pretty(&info)?))
            }
            "config" | "sub" | "unsub" | "gsub" | "gunsub" if !self.can_configure(&msg).await => {
                "Only admins of this chat can do that".into()
            }
            "config" => self.edit_config(chat.0, |cfg| config::config_command(cfg, &args)),
            "sub" | "unsub" => self.edit_config(chat.0, |cfg| config::sub_command(cfg, &args, cmd == "sub")),
            "gsub" | "gunsub" => self.edit_config(chat.0, |cfg| config::group_command(cfg, &args, cmd == "gsub")),
            key if config::SAFE_KEYS.contains(&key) || config::UNSAFE_KEYS.contains(&key) => {
                if !self.can_configure(&msg).await {
                    return Ok(());
                }
                args.insert(0, cmd.clone());
                self.edit_config(chat.0, |cfg| config::config_command(cfg, &args))
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
                let id = self.s().chat_id;
                let info = self.tg.get_chat(ChatId(id)).await?;
                let name = escape(info.title().or(info.username()).unwrap_or("-"));
                match info
                    .username()
                    .map(|u| format!("https://t.me/{u}"))
                    .or(info.invite_link().map(String::from))
                {
                    Some(link) => format!("Chat: <a href=\"{}\">{name}</a> -> <code>{id}</code>", escape(&link)),
                    None => format!("Chat: {name} -> <code>{id}</code>"),
                }
            }
            "settings" => self.settings_command(&args),
            "restart" => {
                *self.restart_in.lock().unwrap() = Some(chat);
                if let Some(token) = self.shutdown.get() {
                    let _ = token.shutdown().map(drop);
                }
                "Bot is restarting...".into()
            }
            _ => return Ok(()),
        };
        self.tg.send_message(chat, reply).parse_mode(ParseMode::Html).await?;
        Ok(())
    }

    /// /settings [KEY [VALUE...]]
    fn settings_command(&self, args: &[String]) -> String {
        let show = |s: &Settings, key: &str| format!("{key}=<code>{}</code>", escape(&s.get(key).unwrap_or_default()));
        let s = self.s();
        match args {
            [] => settings::RUNTIME_KEYS
                .iter()
                .map(|k| show(&s, k))
                .collect::<Vec<_>>()
                .join("\n"),
            [key, ..] if !settings::RUNTIME_KEYS.contains(&key.to_uppercase().as_str()) => format!(
                "Unknown setting, use one of: {}\nLists: <code>/settings KEY a, b</code> replaces, \
                 <code>KEY +a, b</code> adds, <code>KEY -a</code> removes",
                settings::RUNTIME_KEYS.join(", ")
            ),
            [key] => show(&s, &key.to_uppercase()),
            [key, value @ ..] => {
                let key = key.to_uppercase();
                match self.update_settings(|s| s.set(&key, &value.join(" "))) {
                    Some(e) => escape(&e),
                    None => format!("{} (until restart)", show(&self.s(), &key)),
                }
            }
        }
    }
}

/// The bot can never post to this chat again
fn chat_gone(e: &ApiError) -> bool {
    use ApiError::*;
    matches!(
        e,
        BotBlocked
            | BotKicked
            | BotKickedFromSupergroup
            | BotKickedFromChannel
            | ChatNotFound
            | GroupDeactivated
            | UserDeactivated
    )
}

fn load_subs(path: &PathBuf) -> Map<String, Value> {
    let text = std::fs::read_to_string(path).unwrap_or_default();
    match text.trim() {
        "" => Map::new(),
        text => serde_json::from_str(text).expect("sub_config.json is not a valid json object"),
    }
}

/// Replace the process with a fresh one, reloading .env
#[cfg(unix)]
fn restart(chat: ChatId) -> ! {
    use std::os::unix::process::CommandExt;
    let args = std::env::args().skip(1).filter(|a| !a.starts_with(RESTARTED_ARG));
    let exe = std::env::current_exe().expect("could not find own executable");
    let error = std::process::Command::new(exe)
        .args(args)
        .arg(format!("{RESTARTED_ARG}{chat}"))
        .exec();
    panic!("restart failed: {error}");
}

#[tokio::main]
async fn main() {
    // Override so a /restart picks up changes in .env
    let _ = dotenvy::dotenv_override();
    env_logger::Builder::new()
        .filter_level(log::LevelFilter::Trace)
        .parse_default_env()
        .init();
    let (s, webhook) = settings::from_env();
    log::set_max_level(s.log_level);

    let tg = Bot::new(&s.token);
    let me = tg
        .get_me()
        .await
        .expect("could not reach Telegram, is TELEGRAM_API_TOKEN correct?");
    let db = Danbooru::new(settings::DANBOORU_URL, s.danbooru_user.clone(), s.danbooru_api.clone())
        .await
        .expect("could not reach Danbooru");
    let tracker = std::fs::read_to_string(s.config_folder.join("tracker.txt")).unwrap_or_default();
    log::info!(
        "Start {} as @{}",
        if webhook.is_some() { "webhook" } else { "polling" },
        me.username()
    );

    let app = Arc::new(App {
        subs: Mutex::new(load_subs(&s.config_folder.join("sub_config.json"))),
        tracker: Mutex::new(tracker.split_whitespace().filter_map(|id| id.parse().ok()).collect()),
        last_post: AtomicU64::new(0),
        job: AtomicBool::new(s.auto_start),
        refreshing: AtomicBool::new(false),
        manual: AtomicBool::new(false),
        cancel: AtomicBool::new(false),
        wake: Notify::new(),
        shutdown: OnceLock::new(),
        restart_in: Mutex::new(None),
        username: me.username().to_string(),
        settings: RwLock::new(Arc::new(s)),
        tg: tg.clone(),
        db,
    });

    if let Some(chat) = std::env::args().find_map(|a| a.strip_prefix(RESTARTED_ARG)?.parse().ok()) {
        let _ = tg.send_message(ChatId(chat), "Bot has successfully restarted.").await;
    }

    let scheduler = app.clone();
    tokio::spawn(async move {
        loop {
            if scheduler.job.load(SeqCst) {
                scheduler.refresh(false).await;
            }
            let interval = Duration::from_secs(scheduler.s().reload_interval * 60);
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
        .dependencies(dptree::deps![app.clone()])
        .error_handler(LoggingErrorHandler::new())
        .enable_ctrlc_handler()
        .build();
    let _ = app.shutdown.set(dispatcher.shutdown_token());

    match webhook {
        Some(options) => {
            let listener = webhooks::axum(tg, options).await.expect("could not set up the webhook");
            let errors = LoggingErrorHandler::with_custom_text("Update listener error");
            dispatcher.dispatch_with_listener(listener, errors).await
        }
        None => dispatcher.dispatch().await,
    }

    // Let a running refresh finish its current post so nothing is sent twice
    app.cancel.store(true, SeqCst);
    for _ in 0..120 {
        if !app.refreshing.load(SeqCst) {
            break;
        }
        tokio::time::sleep(Duration::from_millis(500)).await;
    }
    if let Some(chat) = *app.restart_in.lock().unwrap() {
        restart(chat);
    }
}
