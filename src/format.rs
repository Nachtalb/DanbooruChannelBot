use std::{collections::BTreeSet, fmt::Write};

use rand::seq::IteratorRandom;
use serde_json::{Map, Value};
use teloxide::utils::html::escape;
use url::Url;

use crate::{danbooru::Post, settings::Settings};

const CAPTION_LIMIT: usize = 1024;
const TEXT_LIMIT: usize = 4096;

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

/// Only letters, digits and "_" are part of a Telegram hashtag
pub fn clean_tag(tag: &str) -> String {
    tag.chars().filter(|c| c.is_alphanumeric() || *c == '_').collect()
}

pub fn hashtags<'a>(tags: impl IntoIterator<Item = &'a String>) -> String {
    let tags = tags.into_iter().map(|t| clean_tag(t)).filter(|t| !t.is_empty());
    tags.map(|t| format!("#{t}")).collect::<Vec<_>>().join(" ")
}

/// Negated tags ("-tag") must not be in `source`. Strict: all other tags must be in `source`,
/// otherwise at least one.
pub fn match_tags(source: &BTreeSet<String>, check: &[String], strict: bool) -> bool {
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
pub fn is_ok(post: &Post, filter: &BTreeSet<String>) -> bool {
    let filter: Vec<String> = filter.iter().cloned().collect();
    !post.is_banned && !post.is_deleted && match_tags(&post.tags(), &filter, true)
}

/// "hello_world foo" -> "Hello_World Foo"
pub fn title(s: &str) -> String {
    let mut prev_alpha = false;
    s.chars()
        .flat_map(|c| {
            let upper = !prev_alpha;
            prev_alpha = c.is_alphabetic();
            if upper {
                c.to_uppercase().collect::<Vec<_>>()
            } else {
                c.to_lowercase().collect()
            }
        })
        .collect()
}

pub fn source_url(post: &Post) -> Option<Url> {
    let src = match post.pixiv_id {
        Some(id) => format!("https://www.pixiv.net/artworks/{id}"),
        None => post.source.clone(),
    };
    Url::parse(&src)
        .ok()
        .filter(|u| matches!(u.scheme(), "http" | "https") && u.host_str().is_some())
}

fn host(url: &Url) -> &str {
    url.host_str().unwrap_or_default().trim_start_matches("www.")
}

pub fn named_source(post: &Post, src: &Url) -> String {
    let parts: Vec<&str> = host(src).split('.').collect();
    let name = title(parts.iter().rev().nth(1).unwrap_or(&parts[0]));
    match name.as_str() {
        "Twitter" | "X" => format!("{name} - @{}", src.path().split('/').nth(1).unwrap_or_default()),
        "Fanbox" if parts.len() > 2 => format!("{name} - {}", title(parts[parts.len() - 3])),
        _ if !post.tag_string_artist.is_empty() => {
            format!("{name} - {}", title(&post.tag_string_artist))
        }
        _ => name,
    }
}

/// Tags in `shown` come first, the rest is filled up with random tags to `max`
pub fn pick_tags(available: &BTreeSet<String>, shown: &BTreeSet<String>, max: usize) -> Vec<String> {
    let mut tags: Vec<String> = available.intersection(shown).cloned().collect();
    let fill = max.saturating_sub(tags.len());
    let random = available.difference(shown).sample(&mut rand::rng(), fill);
    tags.extend(random.into_iter().cloned());
    tags
}

/// Length of the text Telegram displays, which is what its limits count
fn visible_len(html: &str) -> usize {
    let (mut len, mut in_tag, mut in_entity) = (0, false, false);
    for c in html.chars() {
        match c {
            '<' => in_tag = true,
            '>' if in_tag => in_tag = false,
            '&' if !in_tag => (in_entity, len) = (true, len + 1),
            ';' if in_entity => in_entity = false,
            _ if in_tag || in_entity => {}
            _ => len += 1,
        }
    }
    len
}

/// Build the message for a chat. `chat` is None for the main chat, else the subscribers config.
/// Returns None if the post does not match any of the subscribers groups.
pub fn create_post(post: &Post, chat: Option<&Map<String, Value>>, s: &Settings) -> Option<Outgoing> {
    let get = |key: &str| {
        chat.and_then(|c| c.get(key))
            .or(s.defaults.get(key))
            .cloned()
            .unwrap_or_default()
    };
    let on = |key: &str| truthy(&get(key));
    let text_of = |key: &str| match get(key) {
        Value::String(s) => s,
        Value::Null => String::new(),
        v => v.to_string(),
    };

    let mut head = String::new();
    if let Some(chat) = chat {
        let mut extended = post.tags();
        extended.insert(post.rating_tag().into());
        let cleaned: Vec<String> = extended.iter().map(|t| clean_tag(t)).collect();
        extended.extend(cleaned);

        let groups = chat.get("subs").and_then(Value::as_object).cloned().unwrap_or_default();
        let (group, _) = groups.iter().find(|(name, check)| {
            let check: Vec<String> = serde_json::from_value((*check).clone()).unwrap_or_default();
            match_tags(&extended, &check, *name != "OR")
        })?;
        if on("debug") {
            head += &format!("<pre>matched with group \"{}\"</pre>\n", escape(group));
        }
    }

    let mut general = post.tags();
    if on("artist") {
        general.retain(|t| !post.artists().contains(t));
    }
    if on("characters") {
        general.retain(|t| !post.characters().contains(t));
    }
    let source = source_url(post);

    if on("time") {
        let mut date = String::new();
        if write!(date, "{}", post.created_at.format(&text_of("date_format"))).is_err() {
            date = post.created_at.to_rfc2822();
        }
        head += &format!("\n<b>Posted at:</b> {}", escape(&date));
    }
    if on("id") {
        head += &format!("\n<b>ID:</b> {}", post.id);
    }

    let mut tail = String::new();
    if on("artist") && !post.tag_string_artist.is_empty() {
        tail += &format!("\n<b>Artist:</b> {}", hashtags(&post.artists()));
    }
    if on("characters") && !post.tag_string_character.is_empty() {
        tail += &format!("\n<b>Characters:</b> {}", hashtags(&post.characters()));
    }
    let suffix = text_of("suffix");
    if suffix.contains("{src}") || suffix.contains("{namedsrc}") {
        if let Some(src) = &source {
            let href = escape(src.as_str()).replace('"', "&quot;");
            let named = format!("<a href=\"{href}\">{}</a>", escape(&named_source(post, src)));
            tail += &suffix
                .replace("{src}", &escape(src.as_str()))
                .replace("{namedsrc}", &named);
        }
    } else {
        tail += &suffix;
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

    // Drop random tags (they come last) until the caption fits Telegrams limit
    let limit = if mode == Mode::Text { TEXT_LIMIT } else { CAPTION_LIMIT };
    let mut tags = if on("tags") {
        pick_tags(&general, &s.shown_tags, s.max_tags)
    } else {
        vec![]
    };
    let caption = loop {
        let tag_line = if tags.is_empty() {
            String::new()
        } else {
            format!("\n<b>Tags:</b> {}", hashtags(&tags))
        };
        let caption = format!("{head}{tag_line}{tail}");
        if visible_len(&caption) <= limit || tags.pop().is_none() {
            break caption;
        }
    };

    let mut buttons = Vec::new();
    if on("buttons") {
        buttons.push(("📦".to_string(), Url::parse(&post.link()).unwrap()));
        if let Some(src) = source {
            let icon = match host(&src) {
                "twitter.com" | "x.com" | "t.co" => "🐦",
                "pixiv.net" => "🅿️",
                _ => "🌐",
            };
            buttons.push((icon.into(), src));
        }
        if let (true, Ok(direct)) = (on("direct_button"), Url::parse(post.nice_file_url())) {
            buttons.push(("🖼".into(), direct));
        }
    }

    Some(Outgoing { caption, buttons, mode })
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;
    use crate::settings::test_settings;

    fn set(tags: &[&str]) -> BTreeSet<String> {
        tags.iter().map(|t| t.to_string()).collect()
    }

    fn vec(tags: &[&str]) -> Vec<String> {
        tags.iter().map(|t| t.to_string()).collect()
    }

    fn post(extra: Value) -> Post {
        let mut post = json!({
            "id": 5, "created_at": "2020-04-04T14:08:00.000-04:00", "rating": "g",
            "tag_string": "1girl yuri miku some_artist", "tag_string_artist": "some_artist",
            "tag_string_character": "miku", "source": "https://twitter.com/foo/status/1?a=1&b=2",
            "file_ext": "png", "file_url": "https://cdn.donmai.us/a.png",
        });
        post.as_object_mut().unwrap().extend(extra.as_object().unwrap().clone());
        serde_json::from_value(post).unwrap()
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
        assert_eq!(
            hashtags(&vec(&["hatsune_miku", "6+girls", "(:", "pokémon"])),
            "#hatsune_miku #6girls #pokémon"
        );
        assert_eq!(title("hello_world foo"), "Hello_World Foo");
        assert!(!truthy(&Value::from(0.0)));
        assert!(truthy(&Value::from("x")));
        assert_eq!(visible_len("<b>ab</b> &amp; <a href=\"x\">c</a>"), 6);
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
    fn main_chat_caption() {
        let s = test_settings();
        let out = create_post(&post(json!({})), None, &s).unwrap();
        assert!(out.caption.contains("Posted at:</b> Apr 4 '20 at 14:08"));
        assert!(out.caption.contains("<b>Tags:</b> #1girl #yuri\n"));
        assert!(out.caption.contains("<b>Artist:</b> #some_artist"));
        assert_eq!(
            out.buttons.iter().map(|b| b.0.as_str()).collect::<Vec<_>>(),
            ["📦", "🐦"]
        );
        assert_eq!(out.mode, Mode::Auto);

        let many: Vec<String> = (0..300).map(|i| format!("tag_{i}")).collect();
        let out = create_post(&post(json!({"tag_string": many.join(" ")})), None, &s).unwrap();
        assert!(visible_len(&out.caption) <= CAPTION_LIMIT);

        let out = create_post(&post(json!({"pixiv_id": 7, "rating": "e"})), None, &s).unwrap();
        assert_eq!(out.buttons[1].1.as_str(), "https://www.pixiv.net/artworks/7");
    }

    #[test]
    fn subscriber_caption() {
        let s = test_settings();
        let chat = json!({"subs": {"OR": ["nope", "ratinggeneral"]}, "suffix": "{namedsrc}", "no_file": 1});
        let out = create_post(&post(json!({})), chat.as_object(), &s).unwrap();
        assert_eq!(out.mode, Mode::Text);
        assert!(
            out.caption
                .ends_with("<a href=\"https://twitter.com/foo/status/1?a=1&amp;b=2\">Twitter - @foo</a>")
        );

        let chat = json!({"subs": {"OR": [], "g": ["yuri", "-miku"]}});
        assert!(create_post(&post(json!({})), chat.as_object(), &s).is_none());

        let chat = json!({"subs": {"g": ["yuri", "rating:general"]}, "explicit_file": true});
        assert_eq!(
            create_post(&post(json!({"rating": "e"})), chat.as_object(), &s).map(|o| o.mode),
            None
        );
        let out = create_post(&post(json!({})), chat.as_object(), &s).unwrap();
        assert_eq!(out.mode, Mode::Auto);
    }
}
