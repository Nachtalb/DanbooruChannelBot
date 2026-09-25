use std::{
    collections::BTreeSet,
    io::Cursor,
    path::Path,
    sync::Mutex,
    time::{Duration, Instant},
};

use chrono::{DateTime, FixedOffset};
use reqwest::{StatusCode, header::USER_AGENT};
use serde::Deserialize;
use serde_json::Value;
use tokio::process::Command;

use crate::{Result, settings::DANBOORU_URL};

const TEN_MB: usize = 10 * 1024 * 1024;
/// Danbooru asks to stay around 1 request per second for longer sessions
const REQUEST_INTERVAL: Duration = Duration::from_secs(1);
/// Max page size of /posts.json
pub const PAGE_LIMIT: u64 = 200;

#[derive(Deserialize)]
pub struct Post {
    pub id: u64,
    pub created_at: DateTime<FixedOffset>,
    #[serde(default)]
    pub rating: String,
    pub tag_string: String,
    #[serde(default)]
    pub tag_string_artist: String,
    #[serde(default)]
    pub tag_string_character: String,
    #[serde(default)]
    pub is_banned: bool,
    #[serde(default)]
    pub is_deleted: bool,
    pub pixiv_id: Option<u64>,
    #[serde(default)]
    pub source: String,
    pub file_url: String,
    pub large_file_url: Option<String>,
    pub preview_file_url: Option<String>,
    #[serde(default)]
    pub image_width: u32,
    #[serde(default)]
    pub image_height: u32,
}

fn split(tags: &str) -> BTreeSet<String> {
    tags.split_whitespace().map(String::from).collect()
}

impl Post {
    pub fn tags(&self) -> BTreeSet<String> {
        split(&self.tag_string)
    }

    pub fn artists(&self) -> BTreeSet<String> {
        split(&self.tag_string_artist)
    }

    pub fn characters(&self) -> BTreeSet<String> {
        split(&self.tag_string_character)
    }

    pub fn rating_tag(&self) -> &'static str {
        match self.rating.as_str() {
            "g" => "rating:general",
            "s" => "rating:sensitive",
            "q" => "rating:questionable",
            _ => "rating:explicit",
        }
    }

    pub fn link(&self) -> String {
        format!("{DANBOORU_URL}/posts/{}", self.id)
    }

    /// Ugoira are zips of frames, Danbooru provides a webm sample with the correct timings
    pub fn video_sample_url(&self) -> Option<&str> {
        let large = self.large_file_url.as_deref()?;
        (extension(&self.file_url) == "zip" && matches!(extension(large).as_str(), "mp4" | "webm"))
            .then_some(large)
    }

    pub fn nice_file_url(&self) -> &str {
        self.video_sample_url().unwrap_or(&self.file_url)
    }
}

pub fn extension(url: &str) -> String {
    let path = url.split(['?', '#']).next().unwrap_or_default();
    let file = path.rsplit('/').next().unwrap_or_default();
    file.rsplit_once('.')
        .map(|(_, ext)| ext.to_lowercase())
        .unwrap_or_default()
}

pub struct Danbooru {
    http: reqwest::Client,
    auth: Option<(String, String)>,
    user_agent: String,
    next_request: Mutex<Instant>,
}

impl Danbooru {
    pub async fn new(user: Option<String>, api: Option<String>) -> Result<Self> {
        let version = env!("CARGO_PKG_VERSION");
        let mut db = Self {
            http: reqwest::Client::builder()
                .timeout(Duration::from_secs(120))
                .build()?,
            auth: user.zip(api),
            user_agent: format!("DanbooruChannelBot/{version}"),
            next_request: Mutex::new(Instant::now()),
        };
        if db.auth.is_some() {
            let profile = db.get("/profile.json", &[]).await?;
            let id = profile["id"]
                .as_u64()
                .ok_or("DANBOORU_USERNAME / DANBOORU_API are invalid")?;
            db.user_agent = format!("DanbooruChannelBot/{version} (user #{id})");
        }
        Ok(db)
    }

    async fn throttle(&self) {
        let wait = {
            let mut next = self.next_request.lock().unwrap();
            let now = Instant::now();
            let at = (*next).max(now);
            *next = at + REQUEST_INTERVAL;
            at - now
        };
        tokio::time::sleep(wait).await;
    }

    /// GET with rate limiting and retries on network errors, 429 and 5xx
    async fn request(
        &self,
        url: &str,
        query: &[(&str, String)],
        auth: bool,
    ) -> Result<reqwest::Response> {
        let mut backoff = Duration::from_secs(2);
        loop {
            self.throttle().await;
            let mut req = self
                .http
                .get(url)
                .query(query)
                .header(USER_AGENT, &self.user_agent);
            if let (true, Some((user, api))) = (auth, &self.auth) {
                req = req.basic_auth(user, Some(api));
            }
            let error = match req.send().await {
                Ok(resp)
                    if resp.status() == StatusCode::TOO_MANY_REQUESTS
                        || resp.status().is_server_error() =>
                {
                    format!("status {}", resp.status())
                }
                Ok(resp) => return Ok(resp.error_for_status()?),
                Err(e) => e.to_string(),
            };
            if backoff > Duration::from_secs(16) {
                return Err(format!("GET {url} failed: {error}").into());
            }
            log::warn!("GET {url} failed ({error}), retrying in {backoff:?}");
            tokio::time::sleep(backoff).await;
            backoff *= 2;
        }
    }

    async fn get(&self, path: &str, query: &[(&str, String)]) -> Result<Value> {
        Ok(self
            .request(&format!("{DANBOORU_URL}{path}"), query, true)
            .await?
            .json()
            .await?)
    }

    /// Raw post objects, restricted posts may lack fields (e.g. id, file_url)
    pub async fn posts(&self, tags: &str, limit: u64) -> Result<Vec<Value>> {
        let posts = self
            .get(
                "/posts.json",
                &[("tags", tags.into()), ("limit", limit.to_string())],
            )
            .await?;
        Ok(serde_json::from_value(posts)?)
    }

    pub async fn download(&self, url: &str) -> Result<Vec<u8>> {
        Ok(self.request(url, &[], false).await?.bytes().await?.to_vec())
    }
}

#[derive(Clone, Copy, PartialEq, Debug)]
pub enum Kind {
    Photo,
    Animation,
    Video,
    Document,
}

pub struct Media {
    pub kind: Kind,
    pub name: String,
    /// Original file (webm converted to mp4)
    pub data: Vec<u8>,
    /// Shrunk jpeg if the original exceeds Telegrams photo limits
    pub photo: Option<Vec<u8>>,
    pub duration: Option<u32>,
    pub width: Option<u32>,
    pub height: Option<u32>,
    pub thumb: Option<Vec<u8>>,
}

/// Download the posts file and convert it to something Telegram can display
pub async fn prepare(db: &Danbooru, post: &Post) -> Result<Media> {
    let url = post.video_sample_url().unwrap_or(&post.file_url);
    let mut ext = extension(url);
    let mut data = db.download(url).await?;

    let dir = std::env::temp_dir().join(format!("danbooru-{}", post.id));
    tokio::fs::create_dir_all(&dir).await?;
    let result = async {
        if ext == "webm" {
            log::info!("[{}] Converting webm to mp4", post.id);
            match to_mp4(&data, &dir).await {
                Ok(mp4) => (data, ext) = (mp4, "mp4".into()),
                Err(e) => log::error!("[{}] Conversion failed, sending as file: {e}", post.id),
            }
        }

        let mut media = Media {
            kind: Kind::Document,
            name: format!("{}.{ext}", post.id),
            data,
            photo: None,
            duration: None,
            width: Some(post.image_width).filter(|w| *w > 0),
            height: Some(post.image_height).filter(|h| *h > 0),
            thumb: None,
        };
        match ext.as_str() {
            "jpg" | "jpeg" | "png" | "webp" => {
                let data = media.data.clone();
                match tokio::task::spawn_blocking(move || shrink_photo(&data)).await? {
                    Ok(photo) => (media.kind, media.photo) = (Kind::Photo, photo),
                    Err(e) => log::warn!("[{}] Sending as file, not a valid photo: {e}", post.id),
                }
            }
            "gif" => media.kind = Kind::Animation,
            "mp4" => {
                let file = dir.join("probe.mp4");
                tokio::fs::write(&file, &media.data).await?;
                let (duration, has_audio) = probe(&file).await?;
                media.duration = duration;
                media.kind = if has_audio {
                    Kind::Video
                } else {
                    Kind::Animation
                };
                if let Some(preview) = &post.preview_file_url {
                    media.thumb = db.download(preview).await.ok();
                }
            }
            _ => {}
        }
        Ok(media)
    }
    .await;
    let _ = tokio::fs::remove_dir_all(&dir).await;
    result
}

async fn run(cmd: &mut Command) -> Result<Vec<u8>> {
    let out = cmd.kill_on_drop(true).output().await?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).into_owned().into());
    }
    Ok(out.stdout)
}

async fn to_mp4(data: &[u8], dir: &Path) -> Result<Vec<u8>> {
    let (input, output) = (dir.join("input.webm"), dir.join("output.mp4"));
    tokio::fs::write(&input, data).await?;
    run(Command::new("ffmpeg")
        .args(["-hide_banner", "-y", "-i"])
        .arg(&input)
        // h264 needs even dimensions, yuv420p and faststart for playback in Telegram
        .args([
            "-vf",
            "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
        ])
        .arg(&output))
    .await?;
    Ok(tokio::fs::read(output).await?)
}

/// Returns (duration in seconds, has audio)
async fn probe(file: &Path) -> Result<(Option<u32>, bool)> {
    let out = run(Command::new("ffprobe")
        .args([
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type",
            "-of",
            "json",
        ])
        .arg(file))
    .await?;
    let info: Value = serde_json::from_slice(&out)?;
    let duration = info
        .pointer("/format/duration")
        .and_then(Value::as_str)
        .and_then(|d| d.parse::<f64>().ok());
    let has_audio =
        (info["streams"].as_array().into_iter().flatten()).any(|s| s["codec_type"] == "audio");
    Ok((duration.map(|d| d.round() as u32), has_audio))
}

/// Telegram photos must be <= 10MB, width + height <= 10000 and have an aspect ratio <= 20.
/// Returns None if the original already fits, errors if the ratio makes it unsendable as photo.
pub fn shrink_photo(data: &[u8]) -> Result<Option<Vec<u8>>> {
    let (w, h) = image::ImageReader::new(Cursor::new(data))
        .with_guessed_format()?
        .into_dimensions()?;
    if w.max(h) > 20 * w.min(h) {
        return Err("aspect ratio too extreme for a photo".into());
    }
    if data.len() <= TEN_MB && w + h <= 10000 {
        return Ok(None);
    }
    let image = image::load_from_memory(data)?;
    let (mut w, mut h) = (w, h);
    while w + h > 10000 {
        (w, h) = (w * 3 / 4, h * 3 / 4);
    }
    loop {
        let rgb = image
            .resize(w, h, image::imageops::FilterType::Triangle)
            .to_rgb8();
        let mut out = Vec::new();
        image::codecs::jpeg::JpegEncoder::new_with_quality(&mut out, 90).encode_image(&rgb)?;
        if out.len() <= TEN_MB {
            log::info!(
                "Shrunk photo from {:.2}MB to {:.2}MB",
                data.len() as f64 / 1e6,
                out.len() as f64 / 1e6
            );
            return Ok(Some(out));
        }
        (w, h) = (w * 9 / 10, h * 9 / 10);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn png(w: u32, h: u32) -> Vec<u8> {
        let mut out = Vec::new();
        image::RgbImage::new(w, h)
            .write_to(&mut Cursor::new(&mut out), image::ImageFormat::Png)
            .unwrap();
        out
    }

    #[test]
    fn photos() {
        assert!(shrink_photo(&png(100, 100)).unwrap().is_none());
        let big = shrink_photo(&png(9000, 3000)).unwrap().unwrap();
        let (w, h) = image::load_from_memory(&big)
            .unwrap()
            .to_rgb8()
            .dimensions();
        assert!(w + h <= 10000 && w == 3 * h);
        assert!(shrink_photo(&png(2100, 100)).is_err());
    }

    #[test]
    fn urls() {
        assert_eq!(
            extension("https://cdn.donmai.us/original/a/b/abc.PNG?x=1.2"),
            "png"
        );
        assert_eq!(extension("https://cdn.donmai.us/a.b/abc"), "");
    }
}
