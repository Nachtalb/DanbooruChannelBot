use std::{collections::HashSet, fmt::Write};

use rand::seq::IteratorRandom;
use serde_json::{Map, Value};
use teloxide::utils::html::escape;
use url::Url;

use crate::{danbooru::Post, settings::Settings};

#[derive(PartialEq, Debug)]
pub enum Mode {
    Auto,
    Document,
    Text,
}

pub struct Outgoing {
    pub caption: String,
    pub buttons: Vec<(String, Url)>,
    pub mode: Mode,
}

/// Python like truthiness for the loosely typed chat config values
pub fn truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64() != Some(0.0),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}

pub fn clean_tag(tag: &str) -> String {
    tag.chars().filter(|c| c.is_ascii_alphanumeric() || *c == '_').collect()
}

pub fn hashtags<'a>(tags: impl IntoIterator<Item = &'a String>) -> String {
    let tags = tags.into_iter().map(|t| clean_tag(t)).filter(|t| !t.is_empty());
    tags.map(|t| format!("#{t}")).collect::<Vec<_>>().join(" ")
}

/// Negated tags ("-tag") must not be in `source`. Strict: all other tags must be in `source`,
/// otherwise at least one.
pub fn match_tags(source: &HashSet<String>, check: &[String], strict: bool) -> bool {
    let (bad, good): (Vec<_>, Vec<_>) = check.iter().partition(|t| t.starts_with('-'));
    if bad.iter().any(|t| source.contains(&t[1..])) {
        return false;
    }
    match strict {
        true => good.iter().all(|t| source.contains(*t)),
        false => good.iter().any(|t| source.contains(*t)),
    }
}

/// Every tag in POST_TAG_FILTER must be present, every negated one absent
pub fn is_ok(post: &Post, filter: &HashSet<String>) -> bool {
    let filter: Vec<String> = filter.iter().cloned().collect();
    !post.is_banned && !post.is_deleted && match_tags(&post.tags(), &filter, true)
}

/// Python's str.title()
pub fn title(s: &str) -> String {
    let mut prev_alpha = false;
    s.chars()
        .map(|c| {
            let out = if prev_alpha { c.to_lowercase().to_string() } else { c.to_uppercase().to_string() };
            prev_alpha = c.is_alphabetic();
            out
        })
        .collect()
}

pub fn sauce_url(post: &Post) -> Option<String> {
    if let Some(id) = post.pixiv_id {
        return Some(format!("https://www.pixiv.net/member_illust.php?mode=medium&illust_id={id}"));
    }
    (!post.source.is_empty() && !post.source.starts_with("file://")).then(|| post.source.clone())
}

pub fn named_source(post: &Post, src: &Url) -> String {
    let host = src.host_str().unwrap_or_default();
    let parts: Vec<&str> = host.split('.').collect();
    let mut name = title(parts.iter().rev().nth(1).unwrap_or(&host));
    if name == "Twitter" {
        name += &format!(" - @{}", src.path().split('/').nth(1).unwrap_or_default());
    } else if name == "Fanbox" && parts.len() > 2 {
        name += &format!(" - {}", title(parts[parts.len() - 3]));
    } else if !post.tag_string_artist.is_empty() {
        name += &format!(" - {}", title(&post.tag_string_artist));
    }
    name
}

/// Tags in `shown` are always included, the rest is filled up randomly to `max`
pub fn pick_tags(available: &HashSet<String>, shown: &HashSet<String>, max: usize) -> Vec<String> {
    let mut tags: Vec<String> = available.intersection(shown).cloned().collect();
    tags.sort();
    let mut rest: Vec<&String> = available.difference(shown).collect();
    rest.sort();
    let fill = max.saturating_sub(tags.len());
    tags.extend(rest.into_iter().sample(&mut rand::rng(), fill).into_iter().cloned());
    tags
}

/// Build the message for a chat. `chat` is None for the main chat, else the subscribers config.
/// Returns None if the post does not match any of the subscribers groups.
pub fn create_post(post: &Post, chat: Option<&Map<String, Value>>, s: &Settings) -> Option<Outgoing> {
    let get = |key: &str| chat.and_then(|c| c.get(key)).or(s.defaults.get(key)).cloned().unwrap_or_default();
    let on = |key: &str| truthy(&get(key));
    let str_of = |key: &str| match get(key) {
        Value::String(s) => s,
        Value::Null => String::new(),
        v => v.to_string(),
    };

    let mut caption = String::new();
    let mut tags = post.tags();

    if let Some(chat) = chat {
        let mut extended = tags.clone();
        extended.insert(post.rating_tag().into());
        let cleaned: Vec<String> = extended.iter().map(|t| clean_tag(t)).collect();
        extended.extend(cleaned);

        let groups = chat.get("subs").and_then(Value::as_object).cloned().unwrap_or_default();
        let (group, _) = groups.iter().find(|(name, check)| {
            let check: Vec<String> = serde_json::from_value((*check).clone()).unwrap_or_default();
            match_tags(&extended, &check, *name != "OR")
        })?;
        if on("debug") {
            caption += &format!("<pre>matched with group \"{}\"</pre>\n", escape(group));
        }
    }

    if on("artist") {
        post.artists().iter().for_each(|t| _ = tags.remove(t));
    }
    if on("characters") {
        post.characters().iter().for_each(|t| _ = tags.remove(t));
    }
    let tags = pick_tags(&tags, &s.shown_tags, s.max_tags);
    let source = sauce_url(post).and_then(|s| Url::parse(&s).ok()).filter(|u| u.host_str().is_some());

    if on("time") {
        let mut date = String::new();
        if write!(date, "{}", post.created_at.format(&str_of("date_format"))).is_err() {
            date = post.created_at.to_rfc2822();
        }
        caption += &format!("\n<b>Posted at:</b> {}", escape(&date));
    }
    if on("id") {
        caption += &format!("\n<b>ID:</b> {}", post.id);
    }
    if on("tags") && !tags.is_empty() {
        caption += &format!("\n<b>Tags:</b> {}", hashtags(&tags));
    }
    if on("artist") && !post.tag_string_artist.is_empty() {
        caption += &format!("\n<b>Artist:</b> {}", hashtags(&post.artists()));
    }
    if on("characters") && !post.tag_string_character.is_empty() {
        caption += &format!("\n<b>Characters:</b> {}", hashtags(&post.characters()));
    }
    let suffix = str_of("suffix");
    if suffix.contains("{src}") || suffix.contains("{namedsrc}") {
        if let Some(src) = &source {
            let named = format!("<a href=\"{}\">{}</a>", escape(src.as_str()), escape(&named_source(post, src)));
            caption += &suffix.replace("{src}", src.as_str()).replace("{namedsrc}", &named);
        }
    } else {
        caption += &suffix;
    }

    let mut buttons = Vec::new();
    if on("buttons") {
        let link = Url::parse(&format!("{}/posts/{}", s.danbooru_url, post.id)).unwrap();
        buttons.push(("📦".to_string(), link));
        if let Some(src) = source {
            let icon = match src.host_str().unwrap_or_default().trim_start_matches("www.") {
                "twitter.com" | "t.co" => "🐦",
                "pixiv.net" => "🅿️",
                _ => "🌐",
            };
            buttons.push((icon.into(), src));
        }
        if on("direct_button")
            && let Ok(direct) = Url::parse(post.nice_file_url()) {
                buttons.push(("🖼".into(), direct));
            }
    }

    let mode = if on("no_file") {
        Mode::Text
    } else if on("force_file")
        || (on("explicit_file") && post.rating == "e")
        || (on("questionable_file") && matches!(post.rating.as_str(), "q" | "e"))
    {
        Mode::Document
    } else {
        Mode::Auto
    };

    Some(Outgoing { caption, buttons, mode })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn set(tags: &[&str]) -> HashSet<String> {
        tags.iter().map(|t| t.to_string()).collect()
    }

    fn vec(tags: &[&str]) -> Vec<String> {
        tags.iter().map(|t| t.to_string()).collect()
    }

    #[test]
    fn matching() {
        let src = set(&["a", "b", "c"]);
        assert!(match_tags(&src, &vec(&["a", "b"]), true));
        assert!(!match_tags(&src, &vec(&["a", "x"]), true));
        assert!(match_tags(&src, &vec(&["a", "x"]), false));
        assert!(!match_tags(&src, &vec(&["a", "-c"]), false));
        assert!(!match_tags(&src, &vec(&[]), false));
        assert!(match_tags(&src, &vec(&["-x"]), true));
    }

    #[test]
    fn text_helpers() {
        assert_eq!(hashtags(&vec(&["hatsune_miku", "6+girls", "(:"])), "#hatsune_miku #6girls");
        assert_eq!(title("hello_world foo"), "Hello_World Foo");
        assert!(!truthy(&Value::from(0.0)));
        assert!(truthy(&Value::from("x")));
    }

    #[test]
    fn tag_picking() {
        let available = set(&["1girl", "a", "b", "c"]);
        let tags = pick_tags(&available, &set(&["1girl", "yuri"]), 3);
        assert_eq!(tags.len(), 3);
        assert_eq!(tags[0], "1girl");
        assert_eq!(pick_tags(&available, &set(&["1girl"]), 0), vec(&["1girl"]));
    }

    #[test]
    fn caption_and_subs() {
        let post: Post = serde_json::from_value(serde_json::json!({
            "id": 5, "created_at": "2020-04-04T14:08:00.000-04:00", "rating": "g",
            "tag_string": "1girl yuri miku some_artist", "tag_string_artist": "some_artist",
            "tag_string_character": "miku", "source": "https://twitter.com/foo/status/1",
            "file_url": "https://cdn.donmai.us/a.png",
        }))
        .unwrap();
        let mut s = Settings::from_test();
        s.max_tags = 10;

        let out = create_post(&post, None, &s).unwrap();
        assert!(out.caption.contains("Posted at:</b> Apr 4 '20 at 14:08"));
        assert!(out.caption.contains("<b>Tags:</b> #1girl #yuri\n"));
        assert!(out.caption.contains("<b>Artist:</b> #some_artist"));
        assert_eq!(out.buttons.iter().map(|b| b.0.as_str()).collect::<Vec<_>>(), ["📦", "🐦"]);
        assert_eq!(out.mode, Mode::Auto);

        let chat = serde_json::json!({"subs": {"OR": ["nope", "ratinggeneral"]}, "suffix": "{namedsrc}", "no_file": 1});
        let out = create_post(&post, chat.as_object(), &s).unwrap();
        assert_eq!(out.mode, Mode::Text);
        assert!(out.caption.ends_with("<a href=\"https://twitter.com/foo/status/1\">Twitter - @foo</a>"));

        let chat = serde_json::json!({"subs": {"OR": [], "g": ["yuri", "-miku"]}});
        assert!(create_post(&post, chat.as_object(), &s).is_none());
    }
}
