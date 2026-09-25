use std::{collections::HashSet, env, net::SocketAddr, path::PathBuf, str::FromStr};

use serde_json::{Map, Value, json};
use teloxide::update_listeners::webhooks;

pub struct Settings {
    pub token: String,
    pub admins: Vec<String>,
    pub chat_id: i64,
    pub webhook: Option<webhooks::Options>,
    pub config_folder: PathBuf,
    pub danbooru_url: String,
    pub danbooru_user: Option<String>,
    pub danbooru_api: Option<String>,
    pub auto_start: bool,
    pub grace_period: i64,
    pub search_tags: String,
    pub post_tag_filter: HashSet<String>,
    pub max_tags: usize,
    pub shown_tags: HashSet<String>,
    pub last_100_track: bool,
    pub reload_interval: u64,
    /// Fallback values for the per chat config keys (see `config::SAFE_KEYS`)
    pub defaults: Map<String, Value>,
}

fn var(name: &str) -> Option<String> {
    env::var(name).ok()
}

fn required(name: &str) -> String {
    var(name).unwrap_or_else(|| panic!("You need to define the environmental variable \"{name}\""))
}

fn flag(name: &str, default: bool) -> bool {
    var(name).map_or(default, |v| matches!(v.to_lowercase().as_str(), "1" | "true" | "yes"))
}

fn num<T: FromStr>(name: &str, default: T) -> T {
    var(name).map_or(default, |v| v.trim().parse().unwrap_or_else(|_| panic!("{name} must be a number")))
}

fn list(name: &str, default: &str) -> HashSet<String> {
    let value = var(name).filter(|v| !v.is_empty()).unwrap_or(default.into());
    value.split(',').map(str::trim).filter(|t| !t.is_empty()).map(String::from).collect()
}

impl Settings {
    pub fn from_env() -> Self {
        let token = required("TELEGRAM_API_TOKEN");

        // Telegram posts to the public url, the reverse proxy forwards it to /<token> (as before in python)
        let webhook = flag("WEBHOOK", true).then(|| {
            let host = required("WEBHOOK_HOST");
            let path = var("WEBHOOK_PATH").unwrap_or("danbooru_channel_bot".into());
            let listen = var("WEBHOOK_LISTEN").unwrap_or("0.0.0.0".into());
            let address = SocketAddr::new(listen.parse().expect("WEBHOOK_LISTEN must be an ip"), num("WEBHOOK_PORT", 80));
            let url = format!("https://{host}/{path}").parse().expect("invalid WEBHOOK_HOST / WEBHOOK_PATH");
            log::warn!("Webhook listening to {url} on {address}");
            webhooks::Options::new(address, url).path(format!("/{token}"))
        });

        let defaults = json!({
            "artist": flag("SHOW_ARTIST_TAG", true),
            "buttons": flag("SHOW_BUTTONS", true),
            "characters": flag("SHOW_CHARACTER_TAG", true),
            "date_format": var("DATE_FORMAT").unwrap_or("%b %-d '%y at %H:%M".into()),
            "debug": false,
            "direct_button": flag("DIRECT_BUTTON", false),
            "explicit_file": flag("EXPLICIT_FILE", false),
            "force_file": flag("FORCE_FILE", false),
            "id": flag("SHOW_ID", true),
            "no_file": flag("NO_FILE", false),
            "questionable_file": flag("QUESTIONABLE_FILE", false),
            "suffix": var("SUFFIX").unwrap_or_default(),
            "tags": true,
            "time": flag("SHOW_DATE", true),
        });

        let config_folder = PathBuf::from(var("CONFIG_FOLDER").unwrap_or("data".into()));
        std::fs::create_dir_all(&config_folder).expect("could not create CONFIG_FOLDER");

        Self {
            admins: list("ADMINS", "").into_iter().map(|a| a.trim_start_matches('@').to_lowercase()).collect(),
            chat_id: required("CHAT_ID").trim().parse().expect("CHAT_ID must be a number"),
            token,
            webhook,
            config_folder,
            danbooru_url: "https://danbooru.donmai.us".into(),
            danbooru_user: var("DANBOORU_USERNAME").filter(|v| !v.is_empty()),
            danbooru_api: var("DANBOORU_API").filter(|v| !v.is_empty()),
            auto_start: flag("AUTO_START", true),
            grace_period: num("GRACE_PERIOD", 0),
            search_tags: var("SEARCH_TAGS").unwrap_or("rating:safe".into()),
            post_tag_filter: list("POST_TAG_FILTER", ""),
            max_tags: num("MAX_TAGS", 15),
            shown_tags: list(
                "SHOWN_TAGS",
                "1girl,2girls,3girls,4girls,5girls,6+girls,highres,blue_eyes,blonde_hair,yuri,hololive,animated",
            ),
            last_100_track: flag("LAST_100_TRACK", false),
            reload_interval: num("RELOAD_INTEVAL", 5),
            defaults: match defaults {
                Value::Object(map) => map,
                _ => unreachable!(),
            },
        }
    }
}

#[cfg(test)]
impl Settings {
    pub fn from_test() -> Self {
        // SAFETY: only this function touches the environment in tests
        unsafe {
            env::set_var("TELEGRAM_API_TOKEN", "1:x");
            env::set_var("CHAT_ID", "-100");
            env::set_var("WEBHOOK", "false");
            env::set_var("CONFIG_FOLDER", env::temp_dir().join("danbooru-test"));
        }
        Self::from_env()
    }
}
