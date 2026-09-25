use std::{collections::BTreeSet, env, net::SocketAddr, path::PathBuf, str::FromStr};

use log::LevelFilter;
use rand::distr::{Alphanumeric, SampleString};
use serde_json::{Map, Value, json};
use teloxide::update_listeners::webhooks;

pub const DANBOORU_URL: &str = "https://danbooru.donmai.us";

#[derive(Clone)]
pub struct Settings {
    pub token: String,
    pub admins: BTreeSet<String>,
    pub chat_id: i64,
    pub log_level: LevelFilter,
    pub config_folder: PathBuf,
    pub danbooru_user: Option<String>,
    pub danbooru_api: Option<String>,
    pub auto_start: bool,
    pub grace_period: i64,
    pub search_tags: String,
    pub post_tag_filter: BTreeSet<String>,
    pub max_tags: usize,
    pub shown_tags: BTreeSet<String>,
    pub last_100_track: bool,
    pub reload_interval: u64,
    /// Fallback values for the per chat config keys (see `config::SAFE_KEYS`)
    pub defaults: Map<String, Value>,
}

fn var(name: &str) -> Option<String> {
    env::var(name).ok().filter(|v| !v.trim().is_empty())
}

fn required(name: &str) -> String {
    var(name).unwrap_or_else(|| panic!("You need to define the environment variable {name}"))
}

pub fn parse_bool(v: &str) -> bool {
    matches!(v.trim().to_lowercase().as_str(), "1" | "true" | "yes")
}

fn flag(name: &str, default: bool) -> bool {
    var(name).map_or(default, |v| parse_bool(&v))
}

fn num<T: FromStr>(name: &str, default: T) -> T {
    var(name).map_or(default, |v| {
        v.trim()
            .parse()
            .unwrap_or_else(|_| panic!("{name} must be a number"))
    })
}

pub fn parse_list(v: &str) -> BTreeSet<String> {
    v.split(',')
        .map(str::trim)
        .filter(|t| !t.is_empty())
        .map(String::from)
        .collect()
}

fn list(name: &str, default: &str) -> BTreeSet<String> {
    parse_list(&var(name).unwrap_or(default.into()))
}

fn admin_name(name: &str) -> String {
    name.trim().trim_start_matches('@').to_lowercase()
}

pub fn parse_level(v: &str) -> Option<LevelFilter> {
    match v.trim().to_lowercase().as_str() {
        "warning" => Some(LevelFilter::Warn),
        v => v.parse().ok(),
    }
}

/// Settings plus the webhook options if the bot runs in webhook mode
pub fn from_env() -> (Settings, Option<webhooks::Options>) {
    let webhook = flag("WEBHOOK", false).then(|| {
        let host = required("WEBHOOK_HOST");
        let path = var("WEBHOOK_PATH").unwrap_or("danbooru_channel_bot".into());
        let listen = var("WEBHOOK_LISTEN").unwrap_or("0.0.0.0".into());
        let address = SocketAddr::new(
            listen.parse().expect("WEBHOOK_LISTEN must be an ip"),
            num("WEBHOOK_PORT", 5555),
        );
        let url = format!("https://{host}/{}", path.trim_matches('/'))
            .parse()
            .expect("invalid WEBHOOK_HOST/PATH");
        // Telegram sends the secret with every update, requests without it are rejected
        let secret = Alphanumeric.sample_string(&mut rand::rng(), 64);
        webhooks::Options::new(address, url).secret_token(secret)
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
        "suffix": env::var("SUFFIX").unwrap_or_default().replace("\\n", "\n"),
        "tags": flag("SHOW_TAGS", true),
        "time": flag("SHOW_DATE", true),
    });

    let config_folder = PathBuf::from(var("CONFIG_FOLDER").unwrap_or("data".into()));
    std::fs::create_dir_all(&config_folder).expect("could not create CONFIG_FOLDER");

    let log_level = var("LOG_LEVEL").map(|v| parse_level(&v).expect("invalid LOG_LEVEL"));
    let settings = Settings {
        token: required("TELEGRAM_API_TOKEN"),
        admins: list("ADMINS", "").iter().map(|a| admin_name(a)).collect(),
        chat_id: required("CHAT_ID")
            .trim()
            .parse()
            .expect("CHAT_ID must be a number"),
        log_level: log_level.unwrap_or(if flag("DEBUG", false) {
            LevelFilter::Debug
        } else {
            LevelFilter::Info
        }),
        config_folder,
        danbooru_user: var("DANBOORU_USERNAME"),
        danbooru_api: var("DANBOORU_API"),
        auto_start: flag("AUTO_START", true),
        grace_period: num("GRACE_PERIOD", 300),
        search_tags: var("SEARCH_TAGS").unwrap_or_default(),
        post_tag_filter: list("POST_TAG_FILTER", ""),
        max_tags: num("MAX_TAGS", 15),
        shown_tags: list(
            "SHOWN_TAGS",
            "1girl,2girls,3girls,4girls,5girls,6+girls,highres,blue_eyes,blonde_hair,yuri,animated",
        ),
        last_100_track: flag("LAST_100_TRACK", false),
        reload_interval: num::<u64>("RELOAD_INTERVAL", 5).max(1),
        defaults: defaults.as_object().unwrap().clone(),
    };
    (settings, webhook)
}

pub const RUNTIME_KEYS: &[&str] = &[
    "LOG_LEVEL",
    "SHOWN_TAGS",
    "MAX_TAGS",
    "SEARCH_TAGS",
    "POST_TAG_FILTER",
    "SHOW_ARTIST_TAG",
    "SHOW_CHARACTER_TAG",
    "CHAT_ID",
    "ADMINS",
];

fn join(set: &BTreeSet<String>) -> String {
    set.iter().cloned().collect::<Vec<_>>().join(", ")
}

impl Settings {
    pub fn get(&self, key: &str) -> Option<String> {
        Some(match key {
            "LOG_LEVEL" => self.log_level.to_string(),
            "SHOWN_TAGS" => join(&self.shown_tags),
            "MAX_TAGS" => self.max_tags.to_string(),
            "SEARCH_TAGS" => self.search_tags.clone(),
            "POST_TAG_FILTER" => join(&self.post_tag_filter),
            "SHOW_ARTIST_TAG" => self.defaults["artist"].to_string(),
            "SHOW_CHARACTER_TAG" => self.defaults["characters"].to_string(),
            "CHAT_ID" => self.chat_id.to_string(),
            "ADMINS" => join(&self.admins),
            _ => return None,
        })
    }

    /// Change a setting at runtime (not persisted). Lists are replaced, or with a leading
    /// "+"/"-" the given items are added/removed: `SHOWN_TAGS + yuri, 1girl`
    pub fn set(&mut self, key: &str, value: &str) -> Result<(), String> {
        let edit = |set: &mut BTreeSet<String>, map: fn(&str) -> String| {
            let (action, items) = match value.chars().next() {
                Some(c @ ('+' | '-')) => (Some(c), &value[1..]),
                _ => (None, value),
            };
            let items = parse_list(items)
                .iter()
                .map(|i| map(i))
                .collect::<BTreeSet<_>>();
            match action {
                Some('+') => set.extend(items),
                Some(_) => set.retain(|i| !items.contains(i)),
                None => *set = items,
            }
        };
        fn number<T: FromStr>(key: &str, v: &str) -> Result<T, String> {
            v.trim()
                .parse()
                .map_err(|_| format!("{key} must be a number"))
        }
        match key {
            "LOG_LEVEL" => {
                self.log_level =
                    parse_level(value).ok_or("use one of off, error, warn, info, debug, trace")?;
                log::set_max_level(self.log_level);
            }
            "SHOWN_TAGS" => edit(&mut self.shown_tags, str::to_string),
            "POST_TAG_FILTER" => edit(&mut self.post_tag_filter, str::to_string),
            "ADMINS" => edit(&mut self.admins, admin_name),
            "MAX_TAGS" => self.max_tags = number(key, value)?,
            "CHAT_ID" => self.chat_id = number(key, value)?,
            "SEARCH_TAGS" => self.search_tags = value.trim().into(),
            "SHOW_ARTIST_TAG" => {
                _ = self
                    .defaults
                    .insert("artist".into(), parse_bool(value).into())
            }
            "SHOW_CHARACTER_TAG" => {
                _ = self
                    .defaults
                    .insert("characters".into(), parse_bool(value).into())
            }
            _ => return Err(format!("{key} can't be changed at runtime")),
        }
        Ok(())
    }
}

#[cfg(test)]
pub fn test_settings() -> Settings {
    static ENV: std::sync::Once = std::sync::Once::new();
    // SAFETY: runs once before any test reads the environment
    ENV.call_once(|| unsafe {
        env::set_var("TELEGRAM_API_TOKEN", "1:x");
        env::set_var("CHAT_ID", "-100");
        env::set_var("CONFIG_FOLDER", env::temp_dir().join("danbooru-test"));
    });
    from_env().0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn runtime_settings() {
        let mut s = test_settings();
        s.set("SHOWN_TAGS", "a, b").unwrap();
        s.set("SHOWN_TAGS", "+c").unwrap();
        s.set("SHOWN_TAGS", "-a").unwrap();
        assert_eq!(s.get("SHOWN_TAGS").unwrap(), "b, c");
        s.set("ADMINS", "+@Foo").unwrap();
        assert!(s.admins.contains("foo"));
        s.set("SHOW_ARTIST_TAG", "no").unwrap();
        assert_eq!(s.get("SHOW_ARTIST_TAG").unwrap(), "false");
        assert!(s.set("MAX_TAGS", "x").is_err());
        assert!(s.set("TELEGRAM_API_TOKEN", "x").is_err());
    }
}
