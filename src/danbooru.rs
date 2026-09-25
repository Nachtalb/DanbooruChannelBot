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

const MB: usize = 1024 * 1024;
/// Bot API upload limits
pub const UPLOAD_LIMIT: usize = 50 * MB;
const PHOTO_LIMIT: usize = 10 * MB;
/// Danbooru asks to stay around 1 request per second for longer sessions
const REQUEST_INTERVAL: Duration = Duration::from_millis(if cfg!(test) { 1 } else { 1000 });
/// First retry delay, doubled for each of the 4 retries
const BACKOFF: Duration = Duration::from_millis(if cfg!(test) { 1 } else { 2000 });
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
    pub file_ext: String,
    #[serde(default)]
    pub file_size: usize,
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

    /// Ugoira are zips of frames, Danbooru renders them to a webm sample with the correct timings
    pub fn video_sample_url(&self) -> Option<&str> {
        let large = self.large_file_url.as_deref()?;
        (self.file_ext == "zip" && matches!(extension(large).as_str(), "mp4" | "webm")).then_some(large)
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

/// Posts to send and up to which id everything was looked at
pub struct Batch {
    pub posts: Vec<Post>,
    pub scanned: u64,
}

/// Pick the posts to send from a raw API response, oldest first. `seen` posts are skipped, posts
/// younger than `grace` seconds (and all after them) are left for later, restricted ones
/// (missing fields) are skipped for good and filtered ones only count as scanned.
pub fn select(
    mut raw: Vec<Value>,
    last: u64,
    seen: impl Fn(u64) -> bool,
    grace: i64,
    ok: impl Fn(&Post) -> bool,
    now: DateTime<FixedOffset>,
) -> Batch {
    raw.retain(|p| p["id"].as_u64().is_some_and(|id| !seen(id)));
    raw.sort_by_key(|p| p["id"].as_u64());
    let mut batch = Batch {
        posts: vec![],
        scanned: last,
    };
    for value in raw {
        let id = value["id"].as_u64().unwrap();
        match serde_json::from_value::<Post>(value) {
            Ok(post) if (now - post.created_at).num_seconds() < grace => break,
            Ok(post) if ok(&post) => batch.posts.push(post),
            Ok(_) => {}
            Err(e) => log::debug!("Skip restricted post {id}: {e}"),
        }
        batch.scanned = batch.scanned.max(id);
    }
    batch
}

pub struct Danbooru {
    http: reqwest::Client,
    url: String,
    auth: Option<(String, String)>,
    user_agent: String,
    next_request: Mutex<Instant>,
}

impl Danbooru {
    pub async fn new(url: &str, user: Option<String>, api: Option<String>) -> Result<Self> {
        let version = env!("CARGO_PKG_VERSION");
        let mut db = Self {
            http: reqwest::Client::builder().timeout(Duration::from_secs(120)).build()?,
            url: url.trim_end_matches('/').into(),
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
    async fn request(&self, url: &str, query: &[(&str, String)], auth: bool) -> Result<reqwest::Response> {
        let mut backoff = BACKOFF;
        loop {
            self.throttle().await;
            let mut req = self.http.get(url).query(query).header(USER_AGENT, &self.user_agent);
            if let (true, Some((user, api))) = (auth, &self.auth) {
                req = req.basic_auth(user, Some(api));
            }
            let error = match req.send().await {
                Ok(resp) if resp.status() == StatusCode::TOO_MANY_REQUESTS || resp.status().is_server_error() => {
                    format!("status {}", resp.status())
                }
                Ok(resp) => return Ok(resp.error_for_status()?),
                Err(e) => e.to_string(),
            };
            if backoff > BACKOFF * 8 {
                return Err(format!("GET {url} failed: {error}").into());
            }
            log::warn!("GET {url} failed ({error}), retrying in {backoff:?}");
            tokio::time::sleep(backoff).await;
            backoff *= 2;
        }
    }

    async fn get(&self, path: &str, query: &[(&str, String)]) -> Result<Value> {
        Ok(self
            .request(&format!("{}{path}", self.url), query, true)
            .await?
            .json()
            .await?)
    }

    /// Raw post objects, restricted posts may lack fields (e.g. id, file_url).
    /// `after` pages to the posts directly after that id (without using up a search tag).
    pub async fn posts(&self, tags: &str, limit: u64, after: Option<u64>) -> Result<Vec<Value>> {
        let mut query = vec![("tags", tags.to_string()), ("limit", limit.to_string())];
        if let Some(id) = after {
            query.push(("page", format!("a{id}")));
        }
        Ok(serde_json::from_value(self.get("/posts.json", &query).await?)?)
    }

    pub async fn download(&self, url: &str) -> Result<Vec<u8>> {
        Ok(self.request(url, &[], false).await?.bytes().await?.to_vec())
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum Kind {
    Photo,
    Animation,
    Video,
    Document,
}

pub struct Media {
    pub kind: Kind,
    /// Sent as photo, animation or video
    pub data: Vec<u8>,
    pub name: String,
    /// The untouched original, sent as document
    pub original: Vec<u8>,
    pub original_name: String,
    pub duration: Option<u32>,
    pub width: Option<u32>,
    pub height: Option<u32>,
    pub thumb: Option<Vec<u8>>,
}

/// Download the posts file and convert it to something Telegram displays inline:
/// jpg/png as photo (shrunk to the photo limits), other still images converted to jpg,
/// gif as animation, videos and animated images as H.264 mp4 (animation if silent).
/// Anything else, or anything that fails to convert, is sent as document.
/// Returns None if the file is too big to upload to Telegram.
pub async fn prepare(db: &Danbooru, post: &Post) -> Result<Option<Media>> {
    let url = post.video_sample_url().unwrap_or(&post.file_url);
    let ext = extension(url);
    if url == post.file_url && post.file_size > UPLOAD_LIMIT {
        return Ok(None);
    }
    let original = db.download(url).await?;
    if original.len() > UPLOAD_LIMIT {
        return Ok(None);
    }

    let dir = std::env::temp_dir().join(format!("danbooru-{}-{}", std::process::id(), post.id));
    tokio::fs::create_dir_all(&dir).await?;
    let input = dir.join(format!("input.{ext}"));
    tokio::fs::write(&input, &original).await?;

    let animated = post.tags().contains("animated");
    let converted = match ext.as_str() {
        "gif" => Ok((Kind::Animation, original.clone(), None)),
        "jpg" | "jpeg" | "png" if !animated => photo(original.clone()).await,
        "webp" | "avif" | "jxl" if !animated => {
            async {
                let jpg = dir.join("still.jpg");
                ffmpeg(&[&input], &["-frames:v", "1", "-q:v", "2"], &jpg).await?;
                photo(tokio::fs::read(jpg).await?).await
            }
            .await
        }
        "mp4" | "webm" | "png" | "webp" | "avif" => video(&input, &dir.join("output.mp4")).await,
        _ => Err("no inline preview".into()),
    };
    let _ = tokio::fs::remove_dir_all(&dir).await;

    let (kind, data, duration) = converted.unwrap_or_else(|e| {
        log::info!("[{}] Sending as document: {e}", post.id);
        (Kind::Document, vec![], None)
    });
    let thumb = match (kind, &post.preview_file_url) {
        (Kind::Animation | Kind::Video, Some(preview)) => db.download(preview).await.ok(),
        _ => None,
    };
    let data_ext = match kind {
        Kind::Photo if ext != "png" => "jpg",
        Kind::Animation | Kind::Video if ext != "gif" => "mp4",
        _ => &ext,
    };
    Ok(Some(Media {
        kind,
        data: if kind == Kind::Document { original.clone() } else { data },
        name: format!("{}.{data_ext}", post.id),
        original,
        original_name: format!("{}.{ext}", post.id),
        duration,
        width: Some(post.image_width).filter(|w| *w > 0),
        height: Some(post.image_height).filter(|h| *h > 0),
        thumb,
    }))
}

type Prepared = (Kind, Vec<u8>, Option<u32>);

async fn photo(data: Vec<u8>) -> Result<Prepared> {
    let data = tokio::task::spawn_blocking(move || shrink_photo(&data).map(|p| p.unwrap_or(data))).await??;
    Ok((Kind::Photo, data, None))
}

/// Re-encode to H.264/AAC mp4 unless it already is one Telegram can play
async fn video(input: &Path, output: &Path) -> Result<Prepared> {
    let mut info = probe(input).await?;
    let data = if info.playable && extension(&input.to_string_lossy()) == "mp4" {
        tokio::fs::read(input).await?
    } else {
        let args = [
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            // H.264 needs even dimensions, yuv420p and faststart for playback in Telegram
            "-vf",
            "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
        ];
        ffmpeg(&[input], &args, output).await?;
        info = probe(output).await?;
        tokio::fs::read(output).await?
    };
    if data.len() > UPLOAD_LIMIT {
        return Err("converted video too big".into());
    }
    let kind = if info.has_audio { Kind::Video } else { Kind::Animation };
    Ok((kind, data, info.duration))
}

async fn run(cmd: &mut Command) -> Result<Vec<u8>> {
    let out = cmd.kill_on_drop(true).output().await?;
    if !out.status.success() {
        let stderr = String::from_utf8_lossy(&out.stderr);
        return Err(format!("{:?} failed: {}", cmd.as_std().get_program(), stderr.trim()).into());
    }
    Ok(out.stdout)
}

async fn ffmpeg(inputs: &[&Path], args: &[&str], output: &Path) -> Result<()> {
    let mut cmd = Command::new("ffmpeg");
    cmd.args(["-hide_banner", "-loglevel", "error", "-y"]);
    for input in inputs {
        cmd.arg("-i").arg(input);
    }
    run(cmd.args(args).arg(output)).await.map(drop)
}

struct Probe {
    duration: Option<u32>,
    has_audio: bool,
    /// H.264 in yuv420p, which all Telegram clients play
    playable: bool,
}

async fn probe(file: &Path) -> Result<Probe> {
    let out = run(Command::new("ffprobe")
        .args([
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,pix_fmt",
            "-of",
            "json",
        ])
        .arg(file))
    .await?;
    let info: Value = serde_json::from_slice(&out)?;
    let streams: Vec<&Value> = info["streams"].as_array().into_iter().flatten().collect();
    let video = streams
        .iter()
        .find(|s| s["codec_type"] == "video")
        .ok_or("no video stream")?;
    let duration = info
        .pointer("/format/duration")
        .and_then(Value::as_str)
        .and_then(|d| d.parse::<f64>().ok());
    Ok(Probe {
        duration: duration.map(|d| d.round().max(1.0) as u32),
        has_audio: streams.iter().any(|s| s["codec_type"] == "audio"),
        playable: video["codec_name"] == "h264" && video["pix_fmt"] == "yuv420p",
    })
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
    if data.len() <= PHOTO_LIMIT && w + h <= 10000 {
        return Ok(None);
    }
    let image = image::load_from_memory(data)?;
    let (mut w, mut h) = (w, h);
    while w + h > 10000 {
        (w, h) = (w * 3 / 4, h * 3 / 4);
    }
    loop {
        let rgb = image.resize(w, h, image::imageops::FilterType::Triangle).to_rgb8();
        let mut out = Vec::new();
        image::codecs::jpeg::JpegEncoder::new_with_quality(&mut out, 90).encode_image(&rgb)?;
        if out.len() <= PHOTO_LIMIT {
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
    use std::sync::Arc;

    use serde_json::json;
    use tokio::{
        io::{AsyncReadExt, AsyncWriteExt},
        net::TcpListener,
    };

    use super::*;

    type Handler = Box<dyn Fn(usize, &str) -> (u16, Vec<u8>) + Send + Sync>;

    /// Minimal HTTP server, `handler` gets the request number and path. Records the request heads.
    async fn serve(handler: Handler) -> (String, Arc<Mutex<Vec<String>>>) {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        let requests = Arc::new(Mutex::new(vec![]));
        let log = requests.clone();
        tokio::spawn(async move {
            let mut n = 0;
            loop {
                let (mut socket, _) = listener.accept().await.unwrap();
                let mut head = vec![0; 8192];
                let len = socket.read(&mut head).await.unwrap();
                let head = String::from_utf8_lossy(&head[..len]).into_owned();
                let path = head.split(' ').nth(1).unwrap_or_default().to_string();
                log.lock().unwrap().push(head);
                let (status, body) = handler(n, &path);
                let header = format!(
                    "HTTP/1.1 {status} X\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                    body.len()
                );
                socket.write_all(header.as_bytes()).await.unwrap();
                socket.write_all(&body).await.unwrap();
                n += 1;
            }
        });
        (url, requests)
    }

    /// Answer the n-th request with the n-th response, the last one repeats
    fn sequence(responses: Vec<(u16, Vec<u8>)>) -> Handler {
        Box::new(move |n, _| responses[n.min(responses.len() - 1)].clone())
    }

    fn post_json(id: u64, extra: Value) -> Value {
        let mut post = json!({
            "id": id, "created_at": "2020-01-01T00:00:00.000-05:00", "rating": "g", "tag_string": "a b",
            "file_ext": "jpg", "file_size": 10, "file_url": format!("https://cdn.donmai.us/{id}.jpg"),
        });
        post.as_object_mut().unwrap().extend(extra.as_object().unwrap().clone());
        post
    }

    #[tokio::test]
    async fn api_requests() {
        let profile = json!({"id": 42}).to_string().into_bytes();
        let posts = json!([post_json(3, json!({}))]).to_string().into_bytes();
        let (url, requests) = serve(sequence(vec![
            (200, profile),
            (429, vec![]),
            (503, vec![]),
            (200, posts),
        ]))
        .await;

        let db = Danbooru::new(&url, Some("user".into()), Some("key".into()))
            .await
            .unwrap();
        let raw = db.posts("1girl rating:g", 200, Some(7)).await.unwrap();
        assert_eq!(raw[0]["id"], 3);

        let requests = requests.lock().unwrap();
        assert_eq!(requests.len(), 4, "retries on 429 and 5xx");
        assert!(requests[0].starts_with("GET /profile.json "));
        assert!(requests[3].starts_with("GET /posts.json?tags=1girl+rating%3Ag&limit=200&page=a7 "));
        let lower = requests[3].to_lowercase();
        assert!(lower.contains("user-agent: danbooruchannelbot/2.0.0 (user #42)\r\n"));
        assert!(
            lower.contains("authorization: basic dxnlcjprzxk=\r\n"),
            "basic auth user:key"
        );
    }

    #[tokio::test]
    async fn api_errors() {
        let (url, requests) = serve(sequence(vec![(500, vec![])])).await;
        let db = Danbooru::new(&url, None, None).await.unwrap();
        assert!(db.posts("", 1, None).await.is_err());
        assert_eq!(requests.lock().unwrap().len(), 5, "gives up after 4 retries");
        assert!(!requests.lock().unwrap()[0].to_lowercase().contains("authorization"));

        let (url, requests) = serve(sequence(vec![(422, br#"{"message": "too many tags"}"#.to_vec())])).await;
        let db = Danbooru::new(&url, None, None).await.unwrap();
        assert!(db.posts("a b c", 1, None).await.is_err());
        assert_eq!(requests.lock().unwrap().len(), 1, "no retry on client errors");

        let (url, _) = serve(sequence(vec![(200, br#"{"success": false}"#.to_vec())])).await;
        assert!(
            Danbooru::new(&url, Some("u".into()), Some("k".into())).await.is_err(),
            "invalid login"
        );
    }

    #[test]
    fn selecting() {
        let now = DateTime::parse_from_rfc3339("2020-01-01T06:00:00Z").unwrap();
        let raw = vec![
            post_json(15, json!({"created_at": "2020-01-01T00:59:00.000-05:00"})), // too young
            post_json(14, json!({})),
            json!({"created_at": "2020-01-01T00:00:00.000-05:00"}), // restricted, no id
            post_json(13, json!({"tag_string": "a"})),              // filtered
            json!({"id": 12, "tag_string": "a b"}),                 // restricted, no file
            post_json(11, json!({})),
            post_json(10, json!({})), // seen
            post_json(16, json!({})), // after a too young one
        ];
        let ok = |p: &Post| p.tags().contains("b");
        let batch = select(raw, 10, |id| id <= 10, 3600, ok, now);
        assert_eq!(batch.posts.iter().map(|p| p.id).collect::<Vec<_>>(), [11, 14]);
        assert_eq!(batch.scanned, 14);

        let batch = select(vec![post_json(3, json!({}))], 9, |_| false, 0, |_| false, now);
        assert_eq!((batch.posts.len(), batch.scanned), (0, 9), "scanned never goes back");
    }

    #[test]
    fn post_urls() {
        let post: Post = serde_json::from_value(post_json(
            1,
            json!({"file_ext": "zip", "file_url": "https://cdn.donmai.us/original/a.zip",
                   "large_file_url": "https://cdn.donmai.us/sample/sample-a.webm"}),
        ))
        .unwrap();
        assert_eq!(post.nice_file_url(), "https://cdn.donmai.us/sample/sample-a.webm");
        assert_eq!(extension("https://cdn.donmai.us/original/a/b/abc.PNG?x=1.2"), "png");
        assert_eq!(extension("https://cdn.donmai.us/a.b/abc"), "");
    }

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
        let (w, h) = image::load_from_memory(&big).unwrap().to_rgb8().dimensions();
        assert!(w + h <= 10000 && w == 3 * h);
        assert!(shrink_photo(&png(2100, 100)).is_err());
    }

    /// Generate a test file with ffmpeg
    fn generate(name: &str, args: &str) -> Vec<u8> {
        let path = std::env::temp_dir().join(format!("danbooru-test-{}-{name}", std::process::id()));
        let status = std::process::Command::new("ffmpeg")
            .args(["-hide_banner", "-loglevel", "error", "-y"])
            .args(args.split_whitespace())
            .arg(&path)
            .status()
            .expect("tests need ffmpeg on the PATH");
        assert!(status.success(), "generating {name}");
        let data = std::fs::read(&path).unwrap();
        std::fs::remove_file(path).unwrap();
        data
    }

    /// Every file type Danbooru serves, prepared from a mock CDN
    #[tokio::test]
    async fn media() {
        // Odd width to test padding for H.264 where we convert
        let video = "-f lavfi -i testsrc=size=321x240:duration=2:rate=10";
        let even = "-f lavfi -i testsrc=size=320x240:duration=2:rate=10";
        let audio = "-f lavfi -i sine=duration=2";
        let files: Vec<(&str, &str, Vec<u8>)> = vec![
            ("jpg", "", generate("a.jpg", &format!("{video} -frames:v 1"))),
            ("png", "", png(64, 32)),
            ("webp", "", generate("a.webp", &format!("{video} -frames:v 1"))),
            ("gif", "animated", generate("a.gif", video)),
            (
                "png",
                "animated",
                generate("a.apng", &format!("{video} -f apng -plays 0")),
            ),
            (
                "webp",
                "animated",
                generate("b.webp", &format!("{video} -loop 0 -c:v libwebp_anim")),
            ),
            (
                "mp4",
                "animated",
                generate("a.mp4", &format!("{even} -c:v libx264 -pix_fmt yuv420p")),
            ),
            (
                "mp4",
                "animated sound",
                generate("b.mp4", &format!("{even} {audio} -c:v libx264 -pix_fmt yuv420p")),
            ),
            (
                "mp4",
                "animated",
                generate("c.mp4", &format!("{even} -c:v libx264 -pix_fmt yuv444p")),
            ),
            (
                "webm",
                "animated sound",
                generate("a.webm", &format!("{video} {audio} -c:v libvpx-vp9 -c:a libopus")),
            ),
            ("swf", "flash", b"FWS".to_vec()),
        ];
        let thumb = generate("t.jpg", &format!("{video} -frames:v 1"));
        let bodies: Vec<Vec<u8>> = files.iter().map(|f| f.2.clone()).collect();
        let (url, _) = serve(Box::new(move |_, path| {
            match path.trim_start_matches('/').split('.').next() {
                Some("thumb") => (200, thumb.clone()),
                Some(i) => (200, bodies[i.parse::<usize>().unwrap()].clone()),
                None => (404, vec![]),
            }
        }))
        .await;
        let db = Danbooru::new(&url, None, None).await.unwrap();

        let mut results = vec![];
        for (i, (ext, tags, data)) in files.iter().enumerate() {
            let post: Post = serde_json::from_value(post_json(
                i as u64,
                json!({"file_ext": ext, "tag_string": tags, "file_size": data.len(),
                       "file_url": format!("{url}/{i}.{ext}"), "preview_file_url": format!("{url}/thumb.jpg")}),
            ))
            .unwrap();
            let media = prepare(&db, &post).await.unwrap().unwrap();
            assert_eq!(&media.original, data);
            if matches!(media.kind, Kind::Animation | Kind::Video) && ext != &"gif" {
                let file = std::env::temp_dir().join(format!("danbooru-test-{}-out.mp4", std::process::id()));
                std::fs::write(&file, &media.data).unwrap();
                let info = probe(&file).await.unwrap();
                assert!(info.playable, "{ext} {tags} must become playable H.264");
                assert_eq!(info.duration, Some(2));
            }
            results.push((media.kind, media.name, media.thumb.is_some()));
        }
        use Kind::*;
        let t = |kind, name: &str, thumb| (kind, name.to_string(), thumb);
        assert_eq!(
            results,
            [
                t(Photo, "0.jpg", false),
                t(Photo, "1.png", false),
                t(Photo, "2.jpg", false),
                t(Animation, "3.gif", true),
                t(Animation, "4.mp4", true),
                t(Animation, "5.mp4", true),
                t(Animation, "6.mp4", true),
                t(Video, "7.mp4", true),
                t(Animation, "8.mp4", true),
                t(Video, "9.mp4", true),
                t(Document, "10.swf", false),
            ]
        );

        let post: Post = serde_json::from_value(post_json(99, json!({"file_size": UPLOAD_LIMIT + 1}))).unwrap();
        assert!(prepare(&db, &post).await.unwrap().is_none(), "too big, no download");
    }
}
