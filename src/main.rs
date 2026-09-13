mod document;
mod pipeline;
mod platform;
use anyhow::{Result, bail};
use clap::{Parser, Subcommand};
use std::path::PathBuf;

#[derive(Parser)]
#[command(
    name = "hugemark",
    version,
    about = "Render huge Markdown as bounded, recoverable PDF chunks"
)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}
#[derive(Subcommand)]
enum Commands {
    Build(Build),
    Plan(Build),
    /// Print Python runtime requirements (also usable with pip -r).
    Requirements,
    /// Print licenses of the embedded MathJax/Mermaid bundles.
    Licenses,
    #[cfg(windows)]
    #[command(name = "__worker", hide = true)]
    Worker {
        #[arg(last = true)]
        command: Vec<std::ffi::OsString>,
    },
}
#[derive(Parser, Debug, Clone)]
pub struct Build {
    pub input: PathBuf,
    #[arg(short, long)]
    pub output: Option<PathBuf>,
    #[arg(long, default_value = ".hugemark-build")]
    pub build_dir: PathBuf,
    #[arg(long)]
    pub resume: bool,
    #[arg(long, default_value_t = 131072)]
    pub chunk_bytes: usize,
    #[arg(long, default_value_t = 120)]
    pub timeout: u64,
    #[arg(long, default_value_t = 1)]
    pub retries: u8,
    #[arg(long, default_value_t = 8)]
    pub max_split_depth: u8,
    #[arg(long, default_value_os_t = platform::default_python())]
    pub python: PathBuf,
    #[arg(long, default_value = "auto")]
    pub chrome: PathBuf,
    #[arg(long, default_value = "Noto Sans")]
    pub font_sans: String,
    #[arg(long, default_value = "Noto Serif CJK SC")]
    pub font_serif: String,
    #[arg(long, default_value = "Noto Sans Mono CJK SC")]
    pub font_mono: String,
    #[arg(long, default_value = "Noto Sans CJK SC")]
    pub font_cjk: String,
    #[arg(long)]
    pub serif: bool,
    #[arg(long)]
    pub allow_remote: bool,
    /// Custom renderer executable: receives HTML path and PDF output path.
    #[arg(long)]
    pub renderer: Option<PathBuf>,
    /// Mermaid theme: default, neutral, dark, forest, or base.
    #[arg(long,default_value="default",value_parser=["default","neutral","dark","forest","base"])]
    pub mermaid_theme: String,
    /// Keep formula/diagram source visible instead of rendering it.
    #[arg(long)]
    pub no_advanced: bool,
    /// Append a local stylesheet after built-in styles.
    #[arg(long)]
    pub css: Option<PathBuf>,
}
fn main() -> Result<()> {
    let cli = Cli::parse();
    let (args, only_plan) = match cli.command {
        Commands::Build(a) => (a, false),
        Commands::Plan(a) => (a, true),
        Commands::Requirements => {
            print!("{}", include_str!("../workers/requirements.txt"));
            return Ok(());
        }
        Commands::Licenses => {
            print!("{}", include_str!("../assets/vendor/LICENSES.txt"));
            return Ok(());
        }
        #[cfg(windows)]
        Commands::Worker { command } => return platform::gate_worker(command),
    };
    if args.chunk_bytes < 8192 {
        bail!("--chunk-bytes must be at least 8192");
    }
    if args.timeout == 0 || args.timeout.checked_mul(1000).is_none() {
        bail!("--timeout must be positive");
    }
    pipeline::build(args, only_plan)
}
