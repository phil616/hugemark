//! Platform process lifetime: Linux subreaper; Windows gated Job Object worker.
#[cfg(windows)]
use anyhow::Context;
use anyhow::Result;
use std::{
    path::PathBuf,
    process::{Child, Command},
};

pub fn default_python() -> PathBuf {
    let local = if cfg!(windows) {
        ".venv/Scripts/python.exe"
    } else {
        ".venv/bin/python"
    };
    if std::path::Path::new(local).is_file() {
        local.into()
    } else if cfg!(windows) {
        "python".into()
    } else {
        "python3".into()
    }
}

#[cfg(windows)]
pub fn gate_worker(args: Vec<std::ffi::OsString>) -> Result<()> {
    use std::io::Read;
    let mut gate = [0];
    std::io::stdin()
        .read_exact(&mut gate)
        .context("parent closed worker gate")?;
    if gate != [1] {
        anyhow::bail!("invalid worker gate");
    }
    let (program, arguments) = args.split_first().context("missing worker command")?;
    let status = Command::new(program).args(arguments).status()?;
    std::process::exit(status.code().unwrap_or(1));
}

#[cfg(windows)]
mod windows {
    use super::*;
    use std::{
        io::Write,
        mem::{size_of, zeroed},
        os::windows::io::AsRawHandle,
        process::Stdio,
    };
    use windows_sys::Win32::{
        Foundation::{CloseHandle, ERROR_MORE_DATA, GetLastError, HANDLE},
        System::{
            JobObjects::*,
            ProcessStatus::{K32GetProcessMemoryInfo, PROCESS_MEMORY_COUNTERS},
            Threading::{OpenProcess, PROCESS_QUERY_INFORMATION, PROCESS_VM_READ},
        },
    };
    pub struct Job(HANDLE);
    impl Job {
        pub fn attach(child: &mut Child) -> Result<Self> {
            unsafe {
                let handle = CreateJobObjectW(std::ptr::null(), std::ptr::null());
                if handle.is_null() {
                    let error = std::io::Error::last_os_error();
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(error.into());
                }
                let job = Self(handle);
                let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = zeroed();
                limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
                if SetInformationJobObject(
                    handle,
                    JobObjectExtendedLimitInformation,
                    &limits as *const _ as _,
                    size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
                ) == 0
                    || AssignProcessToJobObject(handle, child.as_raw_handle()) == 0
                {
                    let e = std::io::Error::last_os_error();
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(e.into());
                }
                child
                    .stdin
                    .take()
                    .context("worker gate missing")?
                    .write_all(&[1])?;
                Ok(job)
            }
        }
        pub fn rss(&self) -> u64 {
            let mut capacity = 64;
            loop {
                let mut buffer = vec![0usize; capacity + 1];
                unsafe {
                    if QueryInformationJobObject(
                        self.0,
                        JobObjectBasicProcessIdList,
                        buffer.as_mut_ptr() as _,
                        (buffer.len() * size_of::<usize>()) as u32,
                        std::ptr::null_mut(),
                    ) == 0
                    {
                        if GetLastError() == ERROR_MORE_DATA && capacity < 65536 {
                            capacity *= 2;
                            continue;
                        }
                        return 0;
                    }
                    let count = *((buffer.as_ptr() as *const u32).add(1)) as usize;
                    let mut rss = 0;
                    for pid in &buffer[1..1 + count.min(capacity)] {
                        let process = OpenProcess(
                            PROCESS_QUERY_INFORMATION | PROCESS_VM_READ,
                            0,
                            *pid as u32,
                        );
                        if !process.is_null() {
                            let mut counters: PROCESS_MEMORY_COUNTERS = zeroed();
                            if K32GetProcessMemoryInfo(
                                process,
                                &mut counters,
                                size_of::<PROCESS_MEMORY_COUNTERS>() as u32,
                            ) != 0
                            {
                                rss += counters.WorkingSetSize as u64 / 1024;
                            }
                            CloseHandle(process);
                        }
                    }
                    return rss;
                }
            }
        }
    }
    impl Drop for Job {
        fn drop(&mut self) {
            unsafe {
                TerminateJobObject(self.0, 1);
                CloseHandle(self.0);
            }
        }
    }
    pub fn gated(command: Command) -> Result<Command> {
        let mut wrapper = Command::new(std::env::current_exe()?);
        wrapper
            .arg("__worker")
            .arg("--")
            .arg(command.get_program())
            .args(command.get_args())
            .stdin(Stdio::piped());
        for (name, value) in command.get_envs() {
            if let Some(v) = value {
                wrapper.env(name, v);
            } else {
                wrapper.env_remove(name);
            }
        }
        if let Some(dir) = command.get_current_dir() {
            wrapper.current_dir(dir);
        }
        Ok(wrapper)
    }
}
#[cfg(windows)]
pub use windows::{Job, gated};
#[cfg(not(windows))]
pub fn gated(command: Command) -> Result<Command> {
    Ok(command)
}
#[cfg(not(windows))]
pub struct Job;
#[cfg(not(windows))]
impl Job {
    pub fn attach(_: &mut Child) -> Result<Self> {
        Ok(Self)
    }
}
