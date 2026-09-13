use crate::{
    Build,
    document::{self, Block, Heading},
};
use anyhow::{Context, Result, bail};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
#[cfg(unix)]
use std::os::unix::process::CommandExt;
use std::{
    fs::{self, File},
    io::Write,
    path::Path,
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};

#[derive(Clone, Serialize, Deserialize)]
pub struct Chunk {
    pub id: String,
    pub depth: u8,
    pub complete: bool,
    pub pdf_hash: Option<String>,
    pub peak_rss_kib: u64,
    pub attempts: u32,
}
#[derive(Serialize, Deserialize)]
pub struct Manifest {
    pub version: u32,
    pub fingerprint: String,
    pub title: String,
    pub headings: Vec<Heading>,
    pub chunks: Vec<Chunk>,
    #[serde(default)]
    pub resources: std::collections::BTreeMap<String, String>,
}
fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn atomic(path: &Path, data: &[u8]) -> Result<()> {
    let temp = path.with_extension("tmp");
    fs::write(&temp, data)?;
    fs::rename(temp, path)?;
    Ok(())
}
fn save(dir: &Path, m: &Manifest) -> Result<()> {
    atomic(&dir.join("manifest.json"), &serde_json::to_vec_pretty(m)?)
}
fn css_font(name: &str) -> String {
    format!(
        "\"{}\"",
        name.replace('\\', "\\\\")
            .replace('"', "\\\"")
            .replace(['\n', '\r'], " ")
            .replace('<', "\\3c ")
    )
}
fn html(blocks: &[Block], base: &str, args: &Build) -> String {
    let font = if args.serif {
        &args.font_serif
    } else {
        &args.font_sans
    };
    format!(
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><base href=\"{}\"><style>:root{{--sans:{};--mono:{};--cjk:{}}}\n{}\n{}</style></head><body><article class=\"markdown-body\">{}</article></body></html>",
        document::escape(base),
        css_font(font),
        css_font(&args.font_mono),
        css_font(&args.font_cjk),
        include_str!("../assets/github.css"),
        include_str!("../assets/print.css"),
        blocks.iter().map(|b| b.html.as_str()).collect::<String>()
    )
}
fn create_chunk(
    dir: &Path,
    blocks: &[Block],
    identity: &str,
    depth: u8,
    base: &str,
    args: &Build,
) -> Result<Chunk> {
    let mut text = html(blocks, base, args);
    if let Some(css) = &args.css {
        let path = fs::canonicalize(css).context("read custom CSS")?;
        let url =
            url::Url::from_file_path(path).map_err(|_| anyhow::anyhow!("invalid CSS path"))?;
        text = text.replace(
            "</head>",
            &format!(
                "<link rel=\"stylesheet\" href=\"{}\"></head>",
                document::escape(url.as_str())
            ),
        );
    }
    // Identical content at two document positions must not share a mutable PDF.
    let id = hash(format!("{identity}\0{text}").as_bytes())[..24].to_string();
    atomic(&dir.join(format!("{id}.html")), text.as_bytes())?;
    atomic(
        &dir.join(format!("{id}.blocks.json")),
        &serde_json::to_vec(blocks)?,
    )?;
    Ok(Chunk {
        id,
        depth,
        complete: false,
        pdf_hash: None,
        peak_rss_kib: 0,
        attempts: 0,
    })
}
// Chromium starts a new process group. Track the complete descendant tree,
// including adopted grandchildren (the coordinator is a Linux subreaper).
#[cfg(target_os = "linux")]
fn worker_processes() -> Vec<(u32, u64)> {
    let mut rows = Vec::new();
    let page_kib = unsafe { libc::sysconf(libc::_SC_PAGESIZE) } as u64 / 1024;
    if let Ok(entries) = fs::read_dir("/proc") {
        for entry in entries.flatten() {
            if let Ok(pid) = entry.file_name().to_string_lossy().parse::<u32>()
                && let Ok(stat) = fs::read_to_string(entry.path().join("stat"))
                && let Some(end) = stat.rfind(')')
            {
                let fields: Vec<_> = stat[end + 2..].split_whitespace().collect();
                if fields.len() > 21 {
                    rows.push((
                        pid,
                        fields[1].parse::<u32>().unwrap_or(0),
                        fields[21].parse::<u64>().unwrap_or(0) * page_kib,
                    ));
                }
            }
        }
    }
    let mut owned = std::collections::HashSet::from([std::process::id()]);
    loop {
        let before = owned.len();
        for &(pid, parent, _) in &rows {
            if owned.contains(&parent) {
                owned.insert(pid);
            }
        }
        if owned.len() == before {
            break;
        }
    }
    rows.into_iter()
        .filter(|(pid, _, _)| owned.contains(pid) && *pid != std::process::id())
        .map(|(pid, _, rss)| (pid, rss))
        .collect()
}
#[cfg(all(not(target_os = "linux"), not(windows)))]
fn worker_processes() -> Vec<(u32, u64)> {
    Vec::new()
}
fn kill_group(child: &mut std::process::Child) {
    #[cfg(unix)]
    {
        // Freeze parents first so no new descendants can race cleanup.
        for (pid, _) in worker_processes() {
            unsafe {
                libc::kill(pid as i32, libc::SIGSTOP);
            }
        }
        for (pid, _) in worker_processes() {
            unsafe {
                libc::kill(pid as i32, libc::SIGKILL);
            }
        }
        unsafe {
            libc::kill(-(child.id() as i32), libc::SIGKILL);
        }
    }
    let _ = child.kill();
    let _ = child.wait();
    #[cfg(target_os = "linux")]
    unsafe {
        while libc::waitpid(-1, std::ptr::null_mut(), libc::WNOHANG) > 0 {}
    }
}
fn run(command: Command, log: &Path, timeout: u64) -> Result<u64> {
    let mut command = crate::platform::gated(command)?;
    let file = File::create(log)?;
    command
        .stdout(Stdio::from(file.try_clone()?))
        .stderr(Stdio::from(file));
    #[cfg(unix)]
    command.process_group(0);
    let mut child = command.spawn().context("start worker")?;
    let job = crate::platform::Job::attach(&mut child)?;
    let start = Instant::now();
    let mut peak = 0;
    loop {
        #[cfg(windows)]
        {
            peak = peak.max(job.rss());
        }
        #[cfg(not(windows))]
        {
            let _ = &job;
            peak = peak.max(worker_processes().iter().map(|(_, rss)| rss).sum());
        }
        match child.try_wait() {
            Ok(Some(status)) => {
                kill_group(&mut child);
                atomic(
                    &log.with_extension("metrics.json"),
                    &serde_json::to_vec(
                        &serde_json::json!({"peak_rss_kib":peak,"elapsed_ms":start.elapsed().as_millis(),"success":status.success()}),
                    )?,
                )?;
                if !status.success() {
                    bail!("worker exited {status}; see {}", log.display());
                }
                return Ok(peak);
            }
            Ok(None) => {}
            Err(e) => {
                kill_group(&mut child);
                return Err(e.into());
            }
        }
        if start.elapsed() > Duration::from_secs(timeout) {
            kill_group(&mut child);
            atomic(
                &log.with_extension("metrics.json"),
                &serde_json::to_vec(
                    &serde_json::json!({"peak_rss_kib":peak,"elapsed_ms":start.elapsed().as_millis(),"success":false,"timeout":true}),
                )?,
            )?;
            bail!("worker timeout after {timeout}s; see {}", log.display());
        }
        thread::sleep(Duration::from_millis(100));
    }
}
fn renderer(args: &Build, dir: &Path, id: &str) -> Command {
    let html = dir.join(format!("{id}.html"));
    let pdf = dir.join(format!("{id}.pdf"));
    if let Some(path) = &args.renderer {
        let mut c = Command::new(path);
        c.arg(html).arg(pdf);
        return c;
    }
    let mut c = Command::new(&args.python);
    c.arg(dir.join("render.py"))
        .arg(html)
        .arg(pdf)
        .arg("--chrome")
        .arg(&args.chrome)
        .arg("--timeout")
        .arg((args.timeout * 1000).to_string());
    c.arg("--mermaid-theme").arg(&args.mermaid_theme);
    if args.no_advanced {
        c.arg("--no-advanced");
    }
    if args.allow_remote {
        c.arg("--allow-remote");
    }
    c
}
fn valid_pdf(path: &Path) -> bool {
    fs::read(path)
        .map(|b| b.starts_with(b"%PDF-") && b.windows(5).rev().take(1024).any(|w| w == b"%%EOF"))
        .unwrap_or(false)
}
struct Lock(File);
impl Lock {
    fn acquire(dir: &Path) -> Result<Self> {
        let f = File::options()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(dir.join("build.lock"))?;
        fs2::FileExt::try_lock_exclusive(&f)
            .with_context(|| format!("another build is using {}", dir.display()))?;
        Ok(Self(f))
    }
}
impl Drop for Lock {
    fn drop(&mut self) {
        let _ = self.0.sync_all();
    }
}
pub fn build(args: Build, only_plan: bool) -> Result<()> {
    #[cfg(target_os = "linux")]
    if unsafe { libc::prctl(libc::PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) } != 0 {
        bail!("cannot enable worker subreaper");
    }
    let source = fs::read_to_string(&args.input).context("read UTF-8 Markdown")?;
    if source.trim().is_empty() {
        bail!("Markdown input is empty");
    }
    let input = fs::canonicalize(&args.input)?;
    let output = args
        .output
        .clone()
        .unwrap_or_else(|| input.with_extension("pdf"));
    if fs::canonicalize(&output).ok().as_ref() == Some(&input) {
        bail!("output must not overwrite input");
    }
    let base = url::Url::from_directory_path(input.parent().unwrap())
        .map_err(|_| anyhow::anyhow!("invalid input directory"))?
        .to_string();
    fs::create_dir_all(&args.build_dir)?;
    let dir = fs::canonicalize(&args.build_dir)?;
    let _lock = Lock::acquire(&dir)?;
    atomic(
        &dir.join("render.py"),
        include_bytes!("../workers/render.py"),
    )?;
    atomic(
        &dir.join("assemble.py"),
        include_bytes!("../workers/assemble.py"),
    )?;
    atomic(
        &dir.join("resources.py"),
        include_bytes!("../workers/resources.py"),
    )?;
    atomic(
        &dir.join("validate.py"),
        include_bytes!("../workers/validate.py"),
    )?;
    for (name, bytes) in [
        (
            "advanced.py",
            include_bytes!("../workers/advanced.py").as_slice(),
        ),
        (
            "mathjax.js",
            include_bytes!("../assets/vendor/mathjax.js").as_slice(),
        ),
        (
            "mermaid.js",
            include_bytes!("../assets/vendor/mermaid.js").as_slice(),
        ),
    ] {
        atomic(&dir.join(name), bytes)?;
    }
    // Performance knobs don't invalidate already rendered content.
    let config = format!(
        "v4|{base}|{}|{}|{}|{}|{}|{}|{:?}|{:?}",
        args.chunk_bytes,
        args.font_sans,
        args.font_serif,
        args.font_mono,
        args.font_cjk,
        args.serif,
        args.chrome,
        args.renderer
    );
    let mut digest = Sha256::new();
    digest.update(std::env::consts::OS.as_bytes());
    digest.update(source.as_bytes());
    digest.update(config.as_bytes());
    digest.update([args.allow_remote as u8, args.no_advanced as u8]);
    digest.update(args.mermaid_theme.as_bytes());
    digest.update(include_bytes!("../workers/advanced.py"));
    digest.update(include_bytes!("../assets/vendor/manifest.json"));
    if let Some(css) = &args.css {
        digest.update(fs::read(css).context("read custom CSS")?);
        digest.update(fs::canonicalize(css)?.to_string_lossy().as_bytes());
    }
    digest.update(include_bytes!("document.rs"));
    digest.update(include_bytes!("../workers/resources.py"));
    digest.update(include_bytes!("../workers/validate.py"));
    digest.update(include_bytes!("../assets/github.css"));
    digest.update(include_bytes!("../assets/print.css"));
    digest.update(include_bytes!("../workers/render.py"));
    digest.update(include_bytes!("../workers/assemble.py"));
    let fingerprint = format!("{:x}", digest.finalize());
    let manifest_path = dir.join("manifest.json");
    let mut manifest: Manifest = if args.resume && manifest_path.exists() {
        let m: Manifest = serde_json::from_slice(&fs::read(&manifest_path)?)?;
        if m.fingerprint != fingerprint {
            bail!("input or rendering settings changed; rebuild without --resume");
        }
        m
    } else {
        let doc = document::parse(&source, args.chunk_bytes / 4)?;
        let mut chunks = Vec::new();
        for (ordinal, blocks) in document::plan(doc.blocks, args.chunk_bytes)
            .into_iter()
            .enumerate()
        {
            chunks.push(create_chunk(
                &dir,
                &blocks,
                &format!("root-{ordinal}"),
                0,
                &base,
                &args,
            )?);
        }
        Manifest {
            version: 2,
            fingerprint,
            title: input
                .file_stem()
                .unwrap_or_default()
                .to_string_lossy()
                .into(),
            headings: doc.headings,
            chunks,
            resources: Default::default(),
        }
    };
    save(&dir, &manifest)?;
    eprintln!(
        "{} bytes, {} chunks; build: {}",
        source.len(),
        manifest.chunks.len(),
        dir.display()
    );
    drop(source);
    if only_plan {
        return Ok(());
    }
    if args.allow_remote && args.resume {
        bail!(
            "--resume with live remote resources is not reproducible; download resources locally first"
        );
    }
    let previous_resources = manifest.resources.clone();
    let mut resource_command = Command::new(&args.python);
    resource_command.arg(dir.join("resources.py")).arg(&dir);
    run(resource_command, &dir.join("resources.log"), args.timeout)?;
    manifest.resources = serde_json::from_slice(&fs::read(dir.join("resources.json"))?)?;
    if args.resume
        && manifest.chunks.iter().any(|c| c.complete)
        && previous_resources != manifest.resources
    {
        bail!("local resources changed; rebuild without --resume");
    }
    save(&dir, &manifest)?;
    let mut i = 0;
    while i < manifest.chunks.len() {
        let chunk = manifest.chunks[i].clone();
        let pdf = dir.join(format!("{}.pdf", chunk.id));
        if chunk.complete
            && valid_pdf(&pdf)
            && chunk.pdf_hash.as_deref() == Some(&hash(&fs::read(&pdf)?))
        {
            eprintln!("cached {}", chunk.id);
            i += 1;
            continue;
        }
        let mut error = None;
        for _ in 0..=args.retries {
            let _ = fs::remove_file(&pdf);
            manifest.chunks[i].attempts += 1;
            manifest.chunks[i].complete = false;
            save(&dir, &manifest)?;
            eprintln!(
                "render {}/{} {} attempt {}",
                i + 1,
                manifest.chunks.len(),
                chunk.id,
                manifest.chunks[i].attempts
            );
            let log = dir.join(format!(
                "{}.attempt-{}.log",
                chunk.id, manifest.chunks[i].attempts
            ));
            let outcome = run(renderer(&args, &dir, &chunk.id), &log, args.timeout);
            if let Ok(bytes) = fs::read(log.with_extension("metrics.json"))
                && let Ok(metrics) = serde_json::from_slice::<serde_json::Value>(&bytes)
            {
                manifest.chunks[i].peak_rss_kib = manifest.chunks[i]
                    .peak_rss_kib
                    .max(metrics["peak_rss_kib"].as_u64().unwrap_or(0));
            }
            match outcome {
                Ok(peak) if valid_pdf(&pdf) => {
                    let mut check = Command::new(&args.python);
                    check.arg(dir.join("validate.py")).arg(&pdf);
                    if let Err(e) = run(check, &log.with_extension("validation.log"), args.timeout)
                    {
                        error = Some(e);
                        continue;
                    }
                    manifest.chunks[i].peak_rss_kib = manifest.chunks[i].peak_rss_kib.max(peak);
                    manifest.chunks[i].pdf_hash = Some(hash(&fs::read(&pdf)?));
                    manifest.chunks[i].complete = true;
                    error = None;
                    break;
                }
                Ok(_) => error = Some(anyhow::anyhow!("worker returned an invalid PDF")),
                Err(e) => error = Some(e),
            }
        }
        if let Some(error) = error {
            let mut blocks: Vec<Block> =
                serde_json::from_slice(&fs::read(dir.join(format!("{}.blocks.json", chunk.id)))?)?;
            if blocks.len() == 1
                && chunk.depth < args.max_split_depth
                && blocks[0].html.len() > 256
                && let Ok(doc) = document::parse(&blocks[0].markdown, blocks[0].html.len() / 2)
                && doc.blocks.len() > 1
            {
                blocks = doc.blocks;
            }
            if chunk.depth >= args.max_split_depth || blocks.len() < 2 {
                save(&dir, &manifest)?;
                return Err(error.context(format!(
                    "chunk {} cannot split further; fix the cause and use --resume",
                    chunk.id
                )));
            }
            let middle = blocks.len() / 2;
            let a = create_chunk(
                &dir,
                &blocks[..middle],
                &format!("{}-a", chunk.id),
                chunk.depth + 1,
                &base,
                &args,
            )?;
            let b = create_chunk(
                &dir,
                &blocks[middle..],
                &format!("{}-b", chunk.id),
                chunk.depth + 1,
                &base,
                &args,
            )?;
            let mut events = File::options()
                .create(true)
                .append(true)
                .open(dir.join("events.jsonl"))?;
            writeln!(
                events,
                "{}",
                serde_json::json!({"event":"split","parent":chunk.id,"children":[a.id,b.id],"error":error.to_string()})
            )?;
            manifest.chunks.splice(i..=i, [a, b]);
            save(&dir, &manifest)?;
        } else {
            save(&dir, &manifest)?;
            i += 1;
        }
    }
    if let Some(parent) = output.parent().filter(|p| !p.as_os_str().is_empty()) {
        fs::create_dir_all(parent)?;
    }
    let mut cmd = Command::new(&args.python);
    cmd.arg(dir.join("assemble.py"))
        .arg(&manifest_path)
        .arg(&output);
    run(cmd, &dir.join("assembly.log"), args.timeout.max(300))?;
    eprintln!("PDF written to {}", output.display());
    Ok(())
}
