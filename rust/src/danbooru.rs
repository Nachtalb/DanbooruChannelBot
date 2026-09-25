use std::{collections::HashSet, io::Cursor, path::Path};

use chrono::{DateTime, FixedOffset};
use serde::Deserialize;
use serde_json::Value;
use tokio::process::Command;

use crate::Result;

const TEN_MB: usize = 10 * 1024 * 1024;

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
    pub pixiv_ugoira_frame_data: Option<Value>,
}

fn split(tags: &str) -> impl Iterator<Item = String> + '_ {
    tags.split_whitespace().map(String::from)
}

impl Post {
    pub fn tags(&self) -> HashSet<String> {
        split(&self.tag_string).collect()
    }

    pub fn artists(&self) -> Vec<String> {
        split(&self.tag_string_artist).collect()
    }

    pub fn characters(&self) -> Vec<String> {
        split(&self.tag_string_character).collect()
    }

    pub fn rating_tag(&self) -> &'static str {
        match self.rating.as_str() {
            "g" => "rating:general",
            "s" => "rating:sensitive",
            "q" => "rating:questionable",
            _ => "rating:explicit",
        }
    }

    fn large_video_url(&self) -> Option<&str> {
        let large = self.large_file_url.as_deref()?;
        (self.file_url.ends_with(".zip") && (large.ends_with(".mp4") || large.ends_with(".webm"))).then_some(large)
    }

    /// Ugoira zips are only downloaded if we have the frame delays to rebuild the video
    pub fn download_url(&self) -> &str {
        let has_frames = self.pixiv_ugoira_frame_data.as_ref().and_then(|d| d.pointer("/data/0")).is_some();
        self.large_video_url().filter(|_| !has_frames).unwrap_or(&self.file_url)
    }

    pub fn nice_file_url(&self) -> &str {
        self.large_video_url().unwrap_or(&self.file_url)
    }
}

pub fn extension(url: &str) -> String {
    let path = url.split(['?', '#']).next().unwrap_or_default();
    path.rsplit_once('.').map(|(_, ext)| ext.to_lowercase()).unwrap_or_default()
}

pub struct Danbooru {
    http: reqwest::Client,
    pub url: String,
    auth: Option<(String, String)>,
}

impl Danbooru {
    pub fn new(url: String, user: Option<String>, api: Option<String>) -> Self {
        let http = reqwest::Client::builder().user_agent("DanbooruChannelBot").build().unwrap();
        Self { http, url, auth: user.zip(api) }
    }

    async fn get(&self, path: &str, query: &[(&str, String)]) -> Result<Value> {
        let mut req = self.http.get(format!("{}{path}", self.url)).query(query);
        if let Some((user, api)) = &self.auth {
            req = req.basic_auth(user, Some(api));
        }
        Ok(req.send().await?.error_for_status()?.json().await?)
    }

    pub async fn posts(&self, limit: u64, tags: &str) -> Result<Vec<Value>> {
        let posts = self.get("/posts.json", &[("limit", limit.to_string()), ("tags", tags.into())]).await?;
        Ok(serde_json::from_value(posts)?)
    }

    pub async fn post(&self, id: u64) -> Result<Value> {
        self.get(&format!("/posts/{id}.json"), &[]).await
    }

    pub async fn download(&self, url: &str) -> Result<Vec<u8>> {
        let mut tries = 0;
        loop {
            match self.http.get(url).send().await.and_then(|r| r.error_for_status()) {
                Ok(resp) => return Ok(resp.bytes().await?.to_vec()),
                Err(e) if tries < 2 => log::warn!("Retry download of {url}: {e}"),
                Err(e) => return Err(e.into()),
            }
            tries += 1;
        }
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
    /// Original (or converted to mp4) file
    pub data: Vec<u8>,
    /// Shrunk version for Telegrams photo limits if needed
    pub photo: Option<Vec<u8>>,
    pub duration: Option<u32>,
    pub thumb: Option<Vec<u8>>,
}

/// Download the posts file and convert it to something Telegram can display
pub async fn prepare(db: &Danbooru, post: &Post) -> Result<Media> {
    let url = post.download_url();
    let mut ext = extension(url);
    let mut data = db.download(url).await?;

    let dir = std::env::temp_dir().join(format!("danbooru-{}", post.id));
    tokio::fs::create_dir_all(&dir).await?;
    let result = async {
        if ext == "webm" || ext == "zip" {
            log::info!("[{}] Converting from \"{ext}\" to \"mp4\"", post.id);
            match to_mp4(post, &data, &ext, &dir).await {
                Ok(mp4) => (data, ext) = (mp4, "mp4".into()),
                Err(e) => log::error!("[{}] Conversion failed: {e}", post.id),
            }
        }

        let mut media = Media {
            kind: Kind::Document,
            name: format!("{}.{ext}", post.id),
            data,
            photo: None,
            duration: None,
            thumb: None,
        };
        match ext.as_str() {
            "jpg" | "jpeg" | "png" => {
                media.kind = Kind::Photo;
                let (data, w, h) = (media.data.clone(), post.image_width, post.image_height);
                media.photo = tokio::task::spawn_blocking(move || shrink_photo(&data, w, h)).await??;
            }
            "gif" => media.kind = Kind::Animation,
            "mp4" => {
                let file = dir.join("probe.mp4");
                tokio::fs::write(&file, &media.data).await?;
                let (duration, has_audio) = probe(&file).await?;
                media.duration = duration;
                media.kind = if has_audio { Kind::Video } else { Kind::Animation };
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
    let out = cmd.output().await?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).into_owned().into());
    }
    Ok(out.stdout)
}

async fn to_mp4(post: &Post, data: &[u8], ext: &str, dir: &Path) -> Result<Vec<u8>> {
    let mut cmd = Command::new("ffmpeg");
    cmd.args(["-hide_banner", "-y"]);
    if ext == "zip" {
        let frames = dir.join("frames");
        zip::ZipArchive::new(Cursor::new(data))?.extract(&frames)?;
        let frame_ext = std::fs::read_dir(&frames)?
            .filter_map(|e| e.ok())
            .map(|e| extension(&e.file_name().to_string_lossy()))
            .next()
            .ok_or("empty ugoira zip")?;
        let delay = (post.pixiv_ugoira_frame_data.as_ref())
            .and_then(|d| d.pointer("/data/0/delay")?.as_f64())
            .filter(|d| *d > 0.0)
            .unwrap_or(66.0);
        cmd.args(["-framerate", &(1000.0 / delay).to_string(), "-pattern_type", "glob", "-i"]);
        cmd.arg(frames.join(format!("*.{frame_ext}")));
    } else {
        let input = dir.join(format!("input.{ext}"));
        tokio::fs::write(&input, data).await?;
        cmd.arg("-i").arg(input);
    }
    let output = dir.join("output.mp4");
    cmd.args(["-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]);
    run(cmd.arg(&output)).await?;
    Ok(tokio::fs::read(output).await?)
}

/// Returns (duration in seconds, has audio)
async fn probe(file: &Path) -> Result<(Option<u32>, bool)> {
    let out = run(Command::new("ffprobe")
        .args(["-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json"])
        .arg(file))
    .await?;
    let info: Value = serde_json::from_slice(&out)?;
    let duration = info.pointer("/format/duration").and_then(Value::as_str).and_then(|d| d.parse::<f64>().ok());
    let has_audio = (info["streams"].as_array().into_iter().flatten()).any(|s| s["codec_type"] == "audio");
    Ok((duration.map(|d| d.round() as u32), has_audio))
}

/// Telegram photos must be <= 10MB and width + height <= 10000
fn shrink_photo(data: &[u8], width: u32, height: u32) -> Result<Option<Vec<u8>>> {
    if data.len() <= TEN_MB && width + height <= 10000 {
        return Ok(None);
    }
    let image = image::load_from_memory(data)?;
    let (mut w, mut h) = (image.width(), image.height());
    while w + h > 10000 {
        (w, h) = (w * 3 / 4, h * 3 / 4);
    }
    loop {
        let rgb = image.resize(w, h, image::imageops::FilterType::Triangle).to_rgb8();
        let mut out = Vec::new();
        image::codecs::jpeg::JpegEncoder::new_with_quality(&mut out, 90).encode_image(&rgb)?;
        if out.len() <= TEN_MB {
            log::info!("Reduced file size from {:.2}MB to {:.2}MB", data.len() as f64 / 1e6, out.len() as f64 / 1e6);
            return Ok(Some(out));
        }
        (w, h) = (w * 9 / 10, h * 9 / 10);
    }
}
