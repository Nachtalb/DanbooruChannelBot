//! Per chat configuration of subscribers, stored in sub_config.json

use std::collections::BTreeSet;

use serde_json::{Map, Value, json};
use teloxide::utils::html::escape;

pub const SAFE_KEYS: &[&str] = &[
    "artist",
    "buttons",
    "characters",
    "date_format",
    "id",
    "suffix",
    "tags",
    "time",
    "no_file",
    "direct_button",
    "force_file",
    "explicit_file",
    "questionable_file",
    "debug",
];
pub const UNSAFE_KEYS: &[&str] = &["subs"];

pub type Config = Map<String, Value>;

pub fn default_config() -> Value {
    json!({
        "time": false,
        "artist": false,
        "id": false,
        "tags": false,
        "characters": false,
        "suffix": "\n{namedsrc}\nPowered by @danbooru_dump",
        "buttons": false,
        "direct_button": false,
        "subs": {"OR": []},
        "force_file": false,
        "no_file": false,
    })
}

fn code(v: impl AsRef<str>) -> String {
    format!("<code>{}</code>", escape(v.as_ref()))
}

fn display(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        Value::Array(a) => a.iter().map(display).collect::<Vec<_>>().join(", "),
        Value::Object(_) => serde_json::to_string_pretty(v).unwrap(),
        v => v.to_string(),
    }
}

pub fn show(cfg: &Config, key: Option<&str>) -> String {
    match key {
        Some(key) => format!("{}={}", escape(key), code(display(cfg.get(key).unwrap_or(&Value::Null)))),
        None => code(display(&Value::Object(cfg.clone()))),
    }
}

/// "true"/"yes" -> bool, numbers -> float, '' or "" -> empty string, else the string itself
pub fn parse_value(raw: &str) -> Value {
    let value = raw.replace("\\n", "\n");
    match value.to_lowercase().as_str() {
        "true" | "yes" => true.into(),
        "false" | "no" => false.into(),
        "''" | "\"\"" => "".into(),
        _ => value.parse::<f64>().ok().filter(|f| f.is_finite()).map_or(value.into(), Value::from),
    }
}

/// /config [key [value...]]
pub fn config_command(cfg: &mut Config, args: &[String]) -> String {
    match args {
        [] => show(cfg, None),
        [key] => show(cfg, Some(key)),
        [key, ..] if UNSAFE_KEYS.contains(&key.as_str()) => format!("{} cannot be changed", code(key)),
        [key, ..] if !SAFE_KEYS.contains(&key.as_str()) => format!("{} cannot be set", code(key)),
        [key, value @ ..] => {
            cfg.insert(key.clone(), parse_value(&value.join(" ")));
            show(cfg, Some(key))
        }
    }
}

fn groups(cfg: &mut Config) -> &mut Config {
    let subs = cfg.entry("subs").or_insert_with(|| json!({}));
    if !subs.is_object() {
        *subs = json!({});
    }
    subs.as_object_mut().unwrap()
}

fn update_group(cfg: &mut Config, group: &str, tags: &[String], add: bool) -> Vec<String> {
    let groups = groups(cfg);
    let current = groups.get(group).and_then(Value::as_array).into_iter().flatten();
    let mut set: BTreeSet<String> = current.filter_map(|t| t.as_str().map(String::from)).collect();
    for tag in tags.iter().map(|t| t.trim_matches('#').to_string()) {
        if add {
            set.insert(tag);
        } else {
            set.remove(&tag);
        }
    }
    let tags: Vec<String> = set.into_iter().collect();
    groups.insert(group.into(), json!(tags));
    tags
}

/// /sub and /unsub: edit the "OR" group
pub fn sub_command(cfg: &mut Config, args: &[String], add: bool) -> String {
    update_group(cfg, "OR", args, add);
    show(cfg, Some("subs"))
}

/// /gsub and /gunsub: edit or show a named group
pub fn group_command(cfg: &mut Config, args: &[String], add: bool) -> String {
    match args {
        [] => show(cfg, Some("subs")),
        [group] if add => match groups(cfg).get(group).map(display).filter(|t| !t.is_empty()) {
            Some(tags) => format!("{}={}", code(group), code(tags)),
            None => format!("No group with the name {} exists", code(group)),
        },
        [group] => match groups(cfg).remove(group) {
            Some(_) => format!("{} was removed", code(group)),
            None => format!("{} does not exist", code(group)),
        },
        [group, tags @ ..] => {
            let tags = update_group(cfg, group, tags, add);
            if tags.is_empty() && !add {
                groups(cfg).remove(group);
                format!("{} was removed due to being empty", code(group))
            } else {
                format!("{}={}", code(group), code(tags.join(", ")))
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(s: &str) -> Vec<String> {
        s.split_whitespace().map(String::from).collect()
    }

    #[test]
    fn commands() {
        let mut cfg = default_config().as_object().unwrap().clone();

        assert_eq!(config_command(&mut cfg, &args("time yes")), "time=<code>true</code>");
        assert_eq!(config_command(&mut cfg, &args("suffix a\\nb")), "suffix=<code>a\nb</code>");
        assert_eq!(config_command(&mut cfg, &args("id 0")), "id=<code>0.0</code>");
        assert_eq!(config_command(&mut cfg, &args("subs x")), "<code>subs</code> cannot be changed");
        assert_eq!(config_command(&mut cfg, &args("nope x")), "<code>nope</code> cannot be set");

        assert_eq!(sub_command(&mut cfg, &args("#b a"), true), "subs=<code>{\n  \"OR\": [\n    \"a\",\n    \"b\"\n  ]\n}</code>");
        sub_command(&mut cfg, &args("a"), false);
        assert_eq!(cfg["subs"]["OR"], json!(["b"]));

        assert_eq!(group_command(&mut cfg, &args("g x y"), true), "<code>g</code>=<code>x, y</code>");
        assert_eq!(group_command(&mut cfg, &args("g"), true), "<code>g</code>=<code>x, y</code>");
        assert_eq!(group_command(&mut cfg, &args("g x y"), false), "<code>g</code> was removed due to being empty");
        assert_eq!(group_command(&mut cfg, &args("g"), false), "<code>g</code> does not exist");
    }
}
