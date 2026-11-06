// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 MacroStat contributors
//
// MacroStat Rust Daemon - Linux evdev / uinput Zero Latency Engine
#![allow(non_camel_case_types)]

use std::collections::{HashMap, HashSet};
use std::fs;
use std::os::unix::io::AsRawFd;
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, OnceLock, RwLock};
use std::thread;
use std::time::{Duration, Instant};

use evdev::uinput::{VirtualDevice, VirtualDeviceBuilder};
use evdev::{AttributeSet, EventType, InputEvent, Key, RelativeAxisType};
use rand::Rng;
use serde::{Deserialize, Serialize};

mod kwin_input;

/// Kayıt/oynatma güvenlik sınırları: tek makroda en fazla 200 bin nokta,
/// iki nokta arasında en fazla 10 dakika beklenir.
const MAX_MOUSE_PATH_POINTS: usize = 200_000;
const MAX_MOUSE_PATH_STEP_MS: i64 = 600_000;
/// Göreli fare olayları bu aralıkta birleştirilir (yaklaşık 250 Hz).
const MOUSE_RECORD_SAMPLE_MS: u64 = 4;
const MOUSE_RECORD_MAX_SECS: u64 = 600;
/// `--watch-restart` modunda yeniden başlatma tuşuna basılınca dönen kod.
/// Arayüz bu kodu görünce motoru yeniden başlatır.
const WATCH_RESTART_EXIT_CODE: i32 = 42;

static PANIC_STOP: AtomicBool = AtomicBool::new(false);
static SHUTDOWN: AtomicBool = AtomicBool::new(false);
/// GUI kaydettiğinde motoru yeniden başlatmadan profili tazelemek için.
static RELOAD: AtomicBool = AtomicBool::new(false);
/// Aynı anda birden fazla makro thread'inin sanal tuş durumunu birbirine
/// karıştırmasını önlemek için tek yürütme kilidi.
static ACTION_LOCK: Mutex<()> = Mutex::new(());

/// X11 oturumunda gerçek imleç konumunu okumak ve imleci bir noktaya taşımak
/// için libX11'i çalışma anında yükler. Wayland oturumunda XWayland imlecin
/// gerçek ekran konumunu güvenilir biçimde bildirmediğinden bu yol kullanılmaz;
/// orada kayıt göreli hareketle, oynatma da imlecin o anki konumundan başlar.
mod x11 {
    use std::ffi::{c_char, c_int, c_uint, c_ulong, c_void, CStr};
    use std::sync::OnceLock;

    type OpenDisplay = unsafe extern "C" fn(*const c_char) -> *mut c_void;
    type CloseDisplay = unsafe extern "C" fn(*mut c_void) -> c_int;
    type DefaultRootWindow = unsafe extern "C" fn(*mut c_void) -> c_ulong;
    type QueryPointer = unsafe extern "C" fn(
        *mut c_void,
        c_ulong,
        *mut c_ulong,
        *mut c_ulong,
        *mut c_int,
        *mut c_int,
        *mut c_int,
        *mut c_int,
        *mut c_uint,
    ) -> c_int;
    type WarpPointer = unsafe extern "C" fn(
        *mut c_void,
        c_ulong,
        c_ulong,
        c_int,
        c_int,
        c_uint,
        c_uint,
        c_int,
        c_int,
    ) -> c_int;
    type Flush = unsafe extern "C" fn(*mut c_void) -> c_int;

    struct Api {
        open: OpenDisplay,
        close: CloseDisplay,
        root: DefaultRootWindow,
        query: QueryPointer,
        warp: WarpPointer,
        flush: Flush,
    }

    unsafe fn symbol<T: Copy>(handle: *mut c_void, name: &[u8]) -> Option<T> {
        debug_assert_eq!(std::mem::size_of::<T>(), std::mem::size_of::<*mut c_void>());
        let ptr = unsafe { libc::dlsym(handle, name.as_ptr().cast()) };
        if ptr.is_null() {
            None
        } else {
            Some(unsafe { std::mem::transmute_copy(&ptr) })
        }
    }

    unsafe fn load() -> Option<Api> {
        // Proje politikası gereği `c"..."` değişmezi kullanılmıyor; lint yalnızca
        // bu satırda, gerekçesiyle susturuluyor.
        #[allow(clippy::manual_c_str_literals)]
        let library =
            CStr::from_bytes_with_nul(b"libX11.so.6\0").expect("libX11 adı NUL ile bitmeli");
        let handle = unsafe { libc::dlopen(library.as_ptr(), libc::RTLD_LAZY) };
        if handle.is_null() {
            return None;
        }
        Some(Api {
            open: unsafe { symbol(handle, b"XOpenDisplay\0") }?,
            close: unsafe { symbol(handle, b"XCloseDisplay\0") }?,
            root: unsafe { symbol(handle, b"XDefaultRootWindow\0") }?,
            query: unsafe { symbol(handle, b"XQueryPointer\0") }?,
            warp: unsafe { symbol(handle, b"XWarpPointer\0") }?,
            flush: unsafe { symbol(handle, b"XFlush\0") }?,
        })
    }

    fn api() -> Option<&'static Api> {
        static API: OnceLock<Option<Api>> = OnceLock::new();
        API.get_or_init(|| unsafe { load() }).as_ref()
    }

    /// Gerçek bir X11 oturumunda mıyız? Wayland'da (XWayland açık olsa bile)
    /// konum sorgusu güvenilir değildir, bu yüzden kapalı tutulur.
    pub fn available() -> bool {
        if std::env::var_os("WAYLAND_DISPLAY").is_some() {
            return false;
        }
        if std::env::var("XDG_SESSION_TYPE")
            .is_ok_and(|value| value.eq_ignore_ascii_case("wayland"))
        {
            return false;
        }
        std::env::var_os("DISPLAY").is_some()
    }

    fn with_display<T>(f: impl FnOnce(&Api, *mut c_void) -> T) -> Option<T> {
        if !available() {
            return None;
        }
        let api = api()?;
        let display = unsafe { (api.open)(std::ptr::null()) };
        if display.is_null() {
            return None;
        }
        let result = f(api, display);
        unsafe {
            (api.close)(display);
        }
        Some(result)
    }

    /// İmlecin kök penceredeki (ekran) konumu.
    pub fn pointer_position() -> Option<(i32, i32)> {
        with_display(|api, display| unsafe {
            let root = (api.root)(display);
            let (mut root_ret, mut child_ret) = (0, 0);
            let (mut root_x, mut root_y, mut win_x, mut win_y) = (0, 0, 0, 0);
            let mut mask = 0;
            let ok = (api.query)(
                display,
                root,
                &mut root_ret,
                &mut child_ret,
                &mut root_x,
                &mut root_y,
                &mut win_x,
                &mut win_y,
                &mut mask,
            );
            (ok != 0).then_some((root_x, root_y))
        })
        .flatten()
    }

    /// İmleci ekran koordinatına taşır. Yalnızca gerçek X11 oturumunda çalışır.
    pub fn warp_pointer(x: i32, y: i32) -> bool {
        with_display(|api, display| unsafe {
            let root = (api.root)(display);
            let ok = (api.warp)(display, 0, root, 0, 0, 0, 0, x, y);
            (api.flush)(display);
            ok != 0
        })
        .unwrap_or(false)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ActionType {
    #[serde(
        alias = "key_down",
        alias = "KEY_DOWN",
        alias = "KeyDown",
        alias = "keyDown"
    )]
    KEY_DOWN,
    #[serde(alias = "key_up", alias = "KEY_UP", alias = "KeyUp", alias = "keyUp")]
    KEY_UP,
    #[serde(
        alias = "key_tap",
        alias = "KEY_TAP",
        alias = "KeyTap",
        alias = "keyTap"
    )]
    KEY_TAP,
    #[serde(
        alias = "mouse_down",
        alias = "MOUSE_DOWN",
        alias = "MouseDown",
        alias = "mouseDown"
    )]
    MOUSE_DOWN,
    #[serde(
        alias = "mouse_up",
        alias = "MOUSE_UP",
        alias = "MouseUp",
        alias = "mouseUp"
    )]
    MOUSE_UP,
    #[serde(
        alias = "mouse_click",
        alias = "MOUSE_CLICK",
        alias = "MouseClick",
        alias = "mouseClick"
    )]
    MOUSE_CLICK,
    #[serde(
        alias = "mouse_move",
        alias = "MOUSE_MOVE",
        alias = "MouseMove",
        alias = "mouseMove"
    )]
    MOUSE_MOVE,
    #[serde(
        alias = "mouse_scroll",
        alias = "MOUSE_SCROLL",
        alias = "MouseScroll",
        alias = "mouseScroll"
    )]
    MOUSE_SCROLL,
    #[serde(
        alias = "mouse_path",
        alias = "MOUSE_PATH",
        alias = "MousePath",
        alias = "mousePath"
    )]
    MOUSE_PATH,
    #[serde(alias = "text", alias = "TEXT", alias = "Text")]
    TEXT,
    #[serde(alias = "delay", alias = "DELAY", alias = "Delay")]
    DELAY,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MacroAction {
    #[serde(default)]
    pub id: String,
    pub r#type: ActionType,
    pub key: Option<String>,
    #[serde(rename = "mouseButton", alias = "mouse_button", default)]
    pub mouse_button: Option<String>,
    #[serde(rename = "delayMs", alias = "delay_ms", default)]
    pub delay_ms: Option<u64>,
    #[serde(rename = "jitterMs", alias = "jitter_ms", default)]
    pub jitter_ms: Option<u64>,
    pub text: Option<String>,
    pub dx: Option<i32>,
    pub dy: Option<i32>,
    #[serde(rename = "scrollDelta", alias = "scroll_delta", default)]
    pub scroll_delta: Option<i32>,
    /// MOUSE_PATH: [geçen_ms, dx, dy] üçlüleri. Süre bir önceki noktadan
    /// bu yana geçen zamandır; ilk nokta kayıt başlangıcından itibaren bekler.
    #[serde(default)]
    pub points: Option<Vec<[i64; 3]>>,
    /// MOUSE_PATH: kaydın başladığı andaki imleç konumu [x, y]. Yalnızca
    /// konumu okunabilen oturumlarda (X11) bulunur; varsa oynatma başında
    /// imleç buraya taşınır.
    #[serde(default)]
    pub start: Option<[i32; 2]>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum TriggerMode {
    #[serde(alias = "once", alias = "ONCE", alias = "Once")]
    ONCE,
    #[serde(
        alias = "while_held",
        alias = "WHILE_HELD",
        alias = "WhileHeld",
        alias = "whileHeld"
    )]
    WHILE_HELD,
    #[serde(
        alias = "toggle_loop",
        alias = "TOGGLE_LOOP",
        alias = "ToggleLoop",
        alias = "toggleLoop"
    )]
    TOGGLE_LOOP,
    #[serde(
        alias = "repeat_count",
        alias = "REPEAT_COUNT",
        alias = "RepeatCount",
        alias = "repeatCount"
    )]
    REPEAT_COUNT,
    #[serde(
        alias = "double_tap",
        alias = "DOUBLE_TAP",
        alias = "DoubleTap",
        alias = "doubleTap"
    )]
    DOUBLE_TAP,
    #[serde(
        alias = "hold_long_press",
        alias = "HOLD_LONG_PRESS",
        alias = "HoldLongPress",
        alias = "holdLongPress",
        alias = "hold"
    )]
    HOLD_LONG_PRESS,
    #[serde(
        alias = "press_and_release",
        alias = "PRESS_AND_RELEASE",
        alias = "PressAndRelease",
        alias = "pressAndRelease"
    )]
    PRESS_AND_RELEASE,
}

fn default_macro_name() -> String {
    "Yeni Makro".to_string()
}
fn default_true() -> bool {
    true
}
fn default_trigger_mode() -> TriggerMode {
    TriggerMode::ONCE
}
fn default_repeat_count() -> u32 {
    1
}
fn default_double_tap_timeout() -> u64 {
    300
}
fn default_hold_duration() -> u64 {
    300
}

/// Kilit zehirlenmiş olsa bile içeriğe erişir.
///
/// Motor tek süreçte çalışır; bir iş parçacığının paniği tüm motoru
/// düşürmemeli. `lock().unwrap()` kilidi zehirleyen bir panikten sonra
/// süreci de sonlandırırdı.
fn lock<T>(mutex: &Mutex<T>) -> std::sync::MutexGuard<'_, T> {
    mutex
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MacroConfig {
    #[serde(default)]
    pub id: String,
    #[serde(default = "default_macro_name")]
    pub name: String,
    #[serde(default = "default_true")]
    pub enabled: bool,
    #[serde(rename = "triggerKey", alias = "trigger_key", default)]
    pub trigger_key: String,
    #[serde(
        rename = "triggerMode",
        alias = "trigger_mode",
        default = "default_trigger_mode"
    )]
    pub trigger_mode: TriggerMode,
    #[serde(
        rename = "repeatCount",
        alias = "repeat_count",
        default = "default_repeat_count"
    )]
    pub repeat_count: u32,
    #[serde(
        rename = "doubleTapTimeoutMs",
        alias = "double_tap_timeout_ms",
        default = "default_double_tap_timeout"
    )]
    pub double_tap_timeout_ms: u64,
    #[serde(
        rename = "holdDurationMs",
        alias = "hold_duration_ms",
        default = "default_hold_duration"
    )]
    pub hold_duration_ms: u64,
    #[serde(rename = "releaseActions", alias = "release_actions", default)]
    pub release_actions: Vec<MacroAction>,
    #[serde(default)]
    pub actions: Vec<MacroAction>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProfileConfig {
    #[serde(default)]
    pub id: String,
    #[serde(default)]
    pub name: String,
    #[serde(rename = "panicKey", alias = "panic_key", default)]
    pub panic_key: String,
    #[serde(rename = "virtualDeviceName", alias = "virtual_device_name", default)]
    pub virtual_device_name: String,
    #[serde(default)]
    pub macros: Vec<MacroConfig>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MultiProfileWrapper {
    #[serde(rename = "activeProfileId", alias = "active_profile_id", default)]
    pub active_profile_id: Option<String>,
    #[serde(default)]
    pub profiles: Vec<ProfileConfig>,
}

fn string_to_key(key_str: &str) -> Option<Key> {
    let clean = key_str.trim().to_uppercase();
    let s = clean.strip_prefix("KEY_").unwrap_or(&clean);

    if let Some(num_str) = s.strip_prefix("CODE_") {
        if let Ok(c) = num_str.parse::<u16>() {
            return Some(Key::new(c));
        }
    }
    if let Ok(c) = s.parse::<u16>() {
        return Some(Key::new(c));
    }

    match s {
        "A" => Some(Key::KEY_A),
        "B" => Some(Key::KEY_B),
        "C" => Some(Key::KEY_C),
        "D" => Some(Key::KEY_D),
        "E" => Some(Key::KEY_E),
        "F" => Some(Key::KEY_F),
        "G" => Some(Key::KEY_G),
        "H" => Some(Key::KEY_H),
        "I" => Some(Key::KEY_I),
        "J" => Some(Key::KEY_J),
        "K" => Some(Key::KEY_K),
        "L" => Some(Key::KEY_L),
        "M" => Some(Key::KEY_M),
        "N" => Some(Key::KEY_N),
        "O" => Some(Key::KEY_O),
        "P" => Some(Key::KEY_P),
        "Q" => Some(Key::KEY_Q),
        "R" => Some(Key::KEY_R),
        "S" => Some(Key::KEY_S),
        "T" => Some(Key::KEY_T),
        "U" => Some(Key::KEY_U),
        "V" => Some(Key::KEY_V),
        "W" => Some(Key::KEY_W),
        "X" => Some(Key::KEY_X),
        "Y" => Some(Key::KEY_Y),
        "Z" => Some(Key::KEY_Z),

        "1" => Some(Key::KEY_1),
        "2" => Some(Key::KEY_2),
        "3" => Some(Key::KEY_3),
        "4" => Some(Key::KEY_4),
        "5" => Some(Key::KEY_5),
        "6" => Some(Key::KEY_6),
        "7" => Some(Key::KEY_7),
        "8" => Some(Key::KEY_8),
        "9" => Some(Key::KEY_9),
        "0" => Some(Key::KEY_0),

        "F1" => Some(Key::KEY_F1),
        "F2" => Some(Key::KEY_F2),
        "F3" => Some(Key::KEY_F3),
        "F4" => Some(Key::KEY_F4),
        "F5" => Some(Key::KEY_F5),
        "F6" => Some(Key::KEY_F6),
        "F7" => Some(Key::KEY_F7),
        "F8" => Some(Key::KEY_F8),
        "F9" => Some(Key::KEY_F9),
        "F10" => Some(Key::KEY_F10),
        "F11" => Some(Key::KEY_F11),
        "F12" => Some(Key::KEY_F12),
        "F13" => Some(Key::KEY_F13),
        "F14" => Some(Key::KEY_F14),
        "F15" => Some(Key::KEY_F15),
        "F16" => Some(Key::KEY_F16),
        "F17" => Some(Key::KEY_F17),
        "F18" => Some(Key::KEY_F18),
        "F19" => Some(Key::KEY_F19),
        "F20" => Some(Key::KEY_F20),
        "F21" => Some(Key::KEY_F21),
        "F22" => Some(Key::KEY_F22),
        "F23" => Some(Key::KEY_F23),
        "F24" => Some(Key::KEY_F24),

        "SPACE" => Some(Key::KEY_SPACE),
        "ENTER" | "RETURN" => Some(Key::KEY_ENTER),
        "ESC" | "ESCAPE" => Some(Key::KEY_ESC),
        "BACKSPACE" => Some(Key::KEY_BACKSPACE),
        "TAB" => Some(Key::KEY_TAB),

        "LEFTSHIFT" | "SHIFT" | "LSHIFT" => Some(Key::KEY_LEFTSHIFT),
        "RIGHTSHIFT" | "RSHIFT" => Some(Key::KEY_RIGHTSHIFT),
        "LEFTCTRL" | "CTRL" | "LCTRL" | "CONTROL" => Some(Key::KEY_LEFTCTRL),
        "RIGHTCTRL" | "RCTRL" => Some(Key::KEY_RIGHTCTRL),
        "LEFTALT" | "ALT" | "LALT" => Some(Key::KEY_LEFTALT),
        "RIGHTALT" | "RALT" => Some(Key::KEY_RIGHTALT),
        "LEFTMETA" | "SUPER" | "META" | "WIN" | "WINDOWS" => Some(Key::KEY_LEFTMETA),
        "RIGHTMETA" => Some(Key::KEY_RIGHTMETA),
        "CAPSLOCK" | "CAPS" => Some(Key::KEY_CAPSLOCK),
        "PAUSE" | "BREAK" => Some(Key::KEY_PAUSE),
        "DELETE" | "DEL" => Some(Key::KEY_DELETE),
        "INSERT" | "INS" => Some(Key::KEY_INSERT),
        "HOME" => Some(Key::KEY_HOME),
        "END" => Some(Key::KEY_END),
        "PAGEUP" | "PGUP" => Some(Key::KEY_PAGEUP),
        "PAGEDOWN" | "PGDN" => Some(Key::KEY_PAGEDOWN),

        // Arrow keys
        "UP" | "ARROWUP" => Some(Key::KEY_UP),
        "DOWN" | "ARROWDOWN" => Some(Key::KEY_DOWN),
        "LEFT_ARROW" | "ARROWLEFT" => Some(Key::KEY_LEFT),
        "RIGHT_ARROW" | "ARROWRIGHT" => Some(Key::KEY_RIGHT),

        // Symbols and punctuation
        "GRAVE" | "TILDE" | "BACKTICK" => Some(Key::KEY_GRAVE),
        "MINUS" | "DASH" => Some(Key::KEY_MINUS),
        "EQUAL" | "EQUALS" => Some(Key::KEY_EQUAL),
        "LEFTBRACE" | "LBRACE" | "BRACKETLEFT" => Some(Key::KEY_LEFTBRACE),
        "RIGHTBRACE" | "RBRACE" | "BRACKETRIGHT" => Some(Key::KEY_RIGHTBRACE),
        "SEMICOLON" => Some(Key::KEY_SEMICOLON),
        "APOSTROPHE" | "QUOTE" => Some(Key::KEY_APOSTROPHE),
        "BACKSLASH" => Some(Key::KEY_BACKSLASH),
        "COMMA" => Some(Key::KEY_COMMA),
        "DOT" | "PERIOD" => Some(Key::KEY_DOT),
        "SLASH" => Some(Key::KEY_SLASH),

        // Numpad
        "KP0" | "KP_0" | "NUMPAD0" => Some(Key::KEY_KP0),
        "KP1" | "KP_1" | "NUMPAD1" => Some(Key::KEY_KP1),
        "KP2" | "KP_2" | "NUMPAD2" => Some(Key::KEY_KP2),
        "KP3" | "KP_3" | "NUMPAD3" => Some(Key::KEY_KP3),
        "KP4" | "KP_4" | "NUMPAD4" => Some(Key::KEY_KP4),
        "KP5" | "KP_5" | "NUMPAD5" => Some(Key::KEY_KP5),
        "KP6" | "KP_6" | "NUMPAD6" => Some(Key::KEY_KP6),
        "KP7" | "KP_7" | "NUMPAD7" => Some(Key::KEY_KP7),
        "KP8" | "KP_8" | "NUMPAD8" => Some(Key::KEY_KP8),
        "KP9" | "KP_9" | "NUMPAD9" => Some(Key::KEY_KP9),
        "KPENTER" => Some(Key::KEY_KPENTER),
        "KPPLUS" => Some(Key::KEY_KPPLUS),
        "KPMINUS" => Some(Key::KEY_KPMINUS),
        "KPASTERISK" => Some(Key::KEY_KPASTERISK),
        "KPSLASH" => Some(Key::KEY_KPSLASH),
        "KPDOT" => Some(Key::KEY_KPDOT),
        "NUMLOCK" => Some(Key::KEY_NUMLOCK),
        "SCROLLLOCK" => Some(Key::KEY_SCROLLLOCK),

        // Mouse buttons
        "BTN_LEFT" | "LEFT" | "MOUSE_1" | "MOUSE1" | "M1" | "LEFTCLICK" => Some(Key::BTN_LEFT),
        "BTN_RIGHT" | "RIGHT" | "MOUSE_2" | "MOUSE2" | "M2" | "RIGHTCLICK" => Some(Key::BTN_RIGHT),
        "BTN_MIDDLE" | "MIDDLE" | "MOUSE_3" | "MOUSE3" | "M3" | "MIDDLECLICK" => {
            Some(Key::BTN_MIDDLE)
        }
        "BTN_SIDE" | "SIDE" | "MOUSE_4" | "MOUSE4" | "M4" | "M4_SIDE" | "BTN_BACK" | "BACK" => {
            Some(Key::BTN_SIDE)
        }
        "BTN_EXTRA" | "EXTRA" | "MOUSE_5" | "MOUSE5" | "M5" | "M5_SIDE" | "BTN_FORWARD"
        | "FORWARD" => Some(Key::BTN_EXTRA),

        _ => None,
    }
}

fn keys_are_equivalent(k1: Key, k2: Key) -> bool {
    if k1 == k2 {
        return true;
    }
    let is_ctrl = (k1 == Key::KEY_LEFTCTRL || k1 == Key::KEY_RIGHTCTRL)
        && (k2 == Key::KEY_LEFTCTRL || k2 == Key::KEY_RIGHTCTRL);
    let is_shift = (k1 == Key::KEY_LEFTSHIFT || k1 == Key::KEY_RIGHTSHIFT)
        && (k2 == Key::KEY_LEFTSHIFT || k2 == Key::KEY_RIGHTSHIFT);
    let is_alt = (k1 == Key::KEY_LEFTALT || k1 == Key::KEY_RIGHTALT)
        && (k2 == Key::KEY_LEFTALT || k2 == Key::KEY_RIGHTALT);
    let is_meta = (k1 == Key::KEY_LEFTMETA || k1 == Key::KEY_RIGHTMETA)
        && (k2 == Key::KEY_LEFTMETA || k2 == Key::KEY_RIGHTMETA);
    is_ctrl || is_shift || is_alt || is_meta
}

fn char_to_evdev_key(c: char) -> Option<(Key, bool)> {
    match c {
        'a'..='z' => {
            let key_name = format!("KEY_{}", c.to_ascii_uppercase());
            string_to_key(&key_name).map(|k| (k, false))
        }
        'A'..='Z' => {
            let key_name = format!("KEY_{}", c);
            string_to_key(&key_name).map(|k| (k, true))
        }
        '0' => Some((Key::KEY_0, false)),
        '1' => Some((Key::KEY_1, false)),
        '2' => Some((Key::KEY_2, false)),
        '3' => Some((Key::KEY_3, false)),
        '4' => Some((Key::KEY_4, false)),
        '5' => Some((Key::KEY_5, false)),
        '6' => Some((Key::KEY_6, false)),
        '7' => Some((Key::KEY_7, false)),
        '8' => Some((Key::KEY_8, false)),
        '9' => Some((Key::KEY_9, false)),
        ' ' => Some((Key::KEY_SPACE, false)),
        '\n' => Some((Key::KEY_ENTER, false)),
        '\t' => Some((Key::KEY_TAB, false)),
        '-' => Some((Key::KEY_MINUS, false)),
        '_' => Some((Key::KEY_MINUS, true)),
        '=' => Some((Key::KEY_EQUAL, false)),
        '+' => Some((Key::KEY_EQUAL, true)),
        '[' => Some((Key::KEY_LEFTBRACE, false)),
        '{' => Some((Key::KEY_LEFTBRACE, true)),
        ']' => Some((Key::KEY_RIGHTBRACE, false)),
        '}' => Some((Key::KEY_RIGHTBRACE, true)),
        ';' => Some((Key::KEY_SEMICOLON, false)),
        ':' => Some((Key::KEY_SEMICOLON, true)),
        '\'' => Some((Key::KEY_APOSTROPHE, false)),
        '"' => Some((Key::KEY_APOSTROPHE, true)),
        ',' => Some((Key::KEY_COMMA, false)),
        '<' => Some((Key::KEY_COMMA, true)),
        '.' => Some((Key::KEY_DOT, false)),
        '>' => Some((Key::KEY_DOT, true)),
        '/' => Some((Key::KEY_SLASH, false)),
        '?' => Some((Key::KEY_SLASH, true)),
        '\\' => Some((Key::KEY_BACKSLASH, false)),
        '|' => Some((Key::KEY_BACKSLASH, true)),
        '`' => Some((Key::KEY_GRAVE, false)),
        '~' => Some((Key::KEY_GRAVE, true)),
        '!' => Some((Key::KEY_1, true)),
        '@' => Some((Key::KEY_2, true)),
        '#' => Some((Key::KEY_3, true)),
        '$' => Some((Key::KEY_4, true)),
        '%' => Some((Key::KEY_5, true)),
        '^' => Some((Key::KEY_6, true)),
        '&' => Some((Key::KEY_7, true)),
        '*' => Some((Key::KEY_8, true)),
        '(' => Some((Key::KEY_9, true)),
        ')' => Some((Key::KEY_0, true)),
        _ => None,
    }
}

/// US-ASCII dışı karakterleri sessizce yutmak yerine süreç başına bir kez uyarır.
fn warn_unsupported_char(c: char) {
    static WARNED: OnceLock<Mutex<HashSet<char>>> = OnceLock::new();
    let warned = WARNED.get_or_init(|| Mutex::new(HashSet::new()));
    if lock(warned).insert(c) {
        eprintln!(
            "[UYARI] '{}' karakteri TEXT eyleminde desteklenmiyor (yalnızca US-ASCII); atlandı.",
            c
        );
    }
}

/// Profilden gelen sanal aygıt adını güvenli biçime indirger.
///
/// NUL ve diğer denetim karakterleri `uinput` adında anlamsızdır; ayrıca
/// ad, hata ayıklama çıktısı ve bildirimlerde görünür. Boş sonuç varsayılana döner.
fn sanitize_device_name(name: &str) -> String {
    let cleaned: String = name.chars().filter(|c| !c.is_control()).collect();
    let trimmed = cleaned.trim();
    let limited: String = trimmed.chars().take(80).collect();
    if limited.is_empty() {
        "MacroStat Virtual Engine".to_string()
    } else {
        limited
    }
}

fn create_virtual_device(name: &str) -> VirtualDevice {
    let dev_name = sanitize_device_name(name);
    let mut keys = AttributeSet::<Key>::new();

    // Standart masaüstü klavye tuşları (1 - 248): A-Z, 0-9, F1-F24, Modifiyeler, Yön ve Numpad
    for code in 1..=248 {
        keys.insert(Key::new(code));
    }

    // Standart masaüstü fare tuşları (272 - 279): Sol, Sağ, Orta, M4, M5, İleri, Geri, Görev
    // ÖNEMLİ: 288-320 (BTN_JOYSTICK, BTN_GAMEPAD) bilerek EKLENMEMİŞTİR.
    // Bu sayede KDE Wayland ve libinput aygıtı doğrudan standart klavye/fare olarak kabul eder.
    keys.insert(Key::BTN_LEFT);
    keys.insert(Key::BTN_RIGHT);
    keys.insert(Key::BTN_MIDDLE);
    keys.insert(Key::BTN_SIDE);
    keys.insert(Key::BTN_EXTRA);
    keys.insert(Key::BTN_FORWARD);
    keys.insert(Key::BTN_BACK);
    keys.insert(Key::BTN_TASK);

    let mut rel_axes = AttributeSet::<RelativeAxisType>::new();
    rel_axes.insert(RelativeAxisType::REL_X);
    rel_axes.insert(RelativeAxisType::REL_Y);
    rel_axes.insert(RelativeAxisType::REL_WHEEL);
    rel_axes.insert(RelativeAxisType::REL_HWHEEL);

    for _ in 0..5 {
        if let Ok(builder) = VirtualDeviceBuilder::new() {
            if let Ok(b2) = builder.name(&dev_name).with_keys(&keys) {
                if let Ok(b3) = b2.with_relative_axes(&rel_axes) {
                    if let Ok(dev) = b3.build() {
                        return dev;
                    }
                }
            }
        }
        thread::sleep(Duration::from_millis(150));
    }

    VirtualDeviceBuilder::new()
        .unwrap()
        .name(&dev_name)
        .with_keys(&keys)
        .unwrap()
        .with_relative_axes(&rel_axes)
        .unwrap()
        .build()
        .expect("Sanal uinput aygıtı oluşturulamadı! Lütfen arayüzdeki 'İzinleri Düzelt & Başlat' butonuna tıklayın.")
}

fn emit_key(dev: &mut VirtualDevice, key: Key, val: i32) {
    let _ = dev.emit(&[
        InputEvent::new(EventType::KEY, key.0, val),
        InputEvent::new(EventType::SYNCHRONIZATION, 0, 0),
    ]);
}

fn release_all_keys(dev: &mut VirtualDevice, pressed_keys: &mut HashSet<Key>) {
    for &key in pressed_keys.iter() {
        let _ = dev.emit(&[InputEvent::new(EventType::KEY, key.0, 0)]);
    }
    let _ = dev.emit(&[InputEvent::new(EventType::SYNCHRONIZATION, 0, 0)]);
    pressed_keys.clear();
}

fn cancellable_sleep(ms: u64, jitter_ms: u64, stop_flag: Option<&Arc<AtomicBool>>) -> bool {
    if ms == 0 {
        return true;
    }
    let mut rng = rand::thread_rng();
    let effective_ms = if jitter_ms > 0 {
        let delta = rng.gen_range(0..=(jitter_ms * 2)) as i64 - jitter_ms as i64;
        (ms as i64 + delta).max(1) as u64
    } else {
        ms
    };
    let start = Instant::now();
    let target = Duration::from_millis(effective_ms);
    while start.elapsed() < target {
        if PANIC_STOP.load(Ordering::SeqCst) || stop_flag.is_some_and(|f| !f.load(Ordering::SeqCst))
        {
            return false;
        }
        let remaining = target - start.elapsed();
        let chunk = remaining.min(Duration::from_millis(4));
        thread::sleep(chunk);
    }
    true
}

fn execute_macro_actions(
    actions: &[MacroAction],
    vdev: &Arc<Mutex<VirtualDevice>>,
    pressed_keys: &Arc<Mutex<HashSet<Key>>>,
    stop_flag: Option<&Arc<AtomicBool>>,
) -> bool {
    // Eylem sıraları serileştirilir: KEY_DOWN/KEY_UP durumu thread'ler arasında
    // karışmaz. Kilit her eylem dizisi/iterasyon sonunda bırakılır, döngüsel
    // makrolar diğer makroları süresiz kilitlemez.
    let _action_guard = ACTION_LOCK
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());

    for action in actions {
        if PANIC_STOP.load(Ordering::SeqCst) || stop_flag.is_some_and(|f| !f.load(Ordering::SeqCst))
        {
            let mut dev = lock(vdev);
            let mut pressed = lock(pressed_keys);
            release_all_keys(&mut dev, &mut pressed);
            return false;
        }

        let mut dev = lock(vdev);
        let mut pressed = lock(pressed_keys);

        match &action.r#type {
            ActionType::KEY_DOWN => {
                let k_str = action.key.as_deref().or(action.mouse_button.as_deref());
                if let Some(s) = k_str {
                    if let Some(key) = string_to_key(s) {
                        emit_key(&mut dev, key, 1);
                        pressed.insert(key);
                    }
                }
            }
            ActionType::KEY_UP => {
                let k_str = action.key.as_deref().or(action.mouse_button.as_deref());
                if let Some(s) = k_str {
                    if let Some(key) = string_to_key(s) {
                        emit_key(&mut dev, key, 0);
                        pressed.remove(&key);
                    }
                }
            }
            ActionType::KEY_TAP => {
                let k_str = action.key.as_deref().or(action.mouse_button.as_deref());
                if let Some(s) = k_str {
                    if let Some(key) = string_to_key(s) {
                        emit_key(&mut dev, key, 1);
                        pressed.insert(key);
                        drop(dev);
                        drop(pressed);
                        let tap_ms = action.delay_ms.unwrap_or(25).max(10);
                        if !cancellable_sleep(tap_ms, 0, stop_flag) {
                            let mut d = lock(vdev);
                            let mut p = lock(pressed_keys);
                            release_all_keys(&mut d, &mut p);
                            return false;
                        }
                        let mut dev2 = lock(vdev);
                        let mut pressed2 = lock(pressed_keys);
                        emit_key(&mut dev2, key, 0);
                        pressed2.remove(&key);
                        drop(dev2);
                        drop(pressed2);
                        if !cancellable_sleep(10, 0, stop_flag) {
                            let mut d = lock(vdev);
                            let mut p = lock(pressed_keys);
                            release_all_keys(&mut d, &mut p);
                            return false;
                        }
                        continue;
                    }
                }
            }
            ActionType::MOUSE_DOWN => {
                let b_str = action.mouse_button.as_deref().or(action.key.as_deref());
                if let Some(s) = b_str {
                    if let Some(btn) = string_to_key(s) {
                        emit_key(&mut dev, btn, 1);
                        pressed.insert(btn);
                    }
                }
            }
            ActionType::MOUSE_UP => {
                let b_str = action.mouse_button.as_deref().or(action.key.as_deref());
                if let Some(s) = b_str {
                    if let Some(btn) = string_to_key(s) {
                        emit_key(&mut dev, btn, 0);
                        pressed.remove(&btn);
                    }
                }
            }
            ActionType::MOUSE_CLICK => {
                let b_str = action.mouse_button.as_deref().or(action.key.as_deref());
                if let Some(s) = b_str {
                    if let Some(btn) = string_to_key(s) {
                        emit_key(&mut dev, btn, 1);
                        pressed.insert(btn);
                        drop(dev);
                        drop(pressed);
                        let click_ms = action.delay_ms.unwrap_or(20).max(10);
                        if !cancellable_sleep(click_ms, 0, stop_flag) {
                            let mut d = lock(vdev);
                            let mut p = lock(pressed_keys);
                            release_all_keys(&mut d, &mut p);
                            return false;
                        }
                        let mut dev2 = lock(vdev);
                        let mut pressed2 = lock(pressed_keys);
                        emit_key(&mut dev2, btn, 0);
                        pressed2.remove(&btn);
                        drop(dev2);
                        drop(pressed2);
                        if !cancellable_sleep(10, 0, stop_flag) {
                            let mut d = lock(vdev);
                            let mut p = lock(pressed_keys);
                            release_all_keys(&mut d, &mut p);
                            return false;
                        }
                        continue;
                    }
                }
            }
            ActionType::MOUSE_MOVE => {
                let dx = action.dx.unwrap_or(0);
                let dy = action.dy.unwrap_or(0);
                let _ = dev.emit(&[
                    InputEvent::new(EventType::RELATIVE, RelativeAxisType::REL_X.0, dx),
                    InputEvent::new(EventType::RELATIVE, RelativeAxisType::REL_Y.0, dy),
                    InputEvent::new(EventType::SYNCHRONIZATION, 0, 0),
                ]);
            }
            ActionType::MOUSE_PATH => {
                let points = action.points.clone().unwrap_or_default();
                drop(dev);
                drop(pressed);
                let cancelled = PANIC_STOP.load(Ordering::SeqCst)
                    || stop_flag.is_some_and(|f| !f.load(Ordering::SeqCst));
                if cancelled {
                    let mut d = lock(vdev);
                    let mut p = lock(pressed_keys);
                    release_all_keys(&mut d, &mut p);
                    return false;
                }
                // Kayıt sırasında başlangıç noktası alındıysa imleci oraya taşı;
                // böylece göreli yol ekranda kayıttakiyle aynı yerde başlar.
                if let Some([x, y]) = action.start {
                    let x = x.clamp(-1_000_000, 1_000_000);
                    let y = y.clamp(-1_000_000, 1_000_000);
                    let moved = x11::warp_pointer(x, y) || kwin_input::move_pointer_absolute(x, y);
                    if moved {
                        println!("[MOUSE_PATH] İmleç başlangıç noktasına taşındı: ({x}, {y})");
                    }
                }
                for point in points.into_iter().take(MAX_MOUSE_PATH_POINTS) {
                    let dt = point[0].clamp(0, MAX_MOUSE_PATH_STEP_MS) as u64;
                    let dx = point[1].clamp(i32::MIN as i64, i32::MAX as i64) as i32;
                    let dy = point[2].clamp(i32::MIN as i64, i32::MAX as i64) as i32;
                    if !cancellable_sleep(dt, 0, stop_flag) {
                        let mut d = lock(vdev);
                        let mut p = lock(pressed_keys);
                        release_all_keys(&mut d, &mut p);
                        return false;
                    }
                    if dx == 0 && dy == 0 {
                        continue;
                    }
                    let mut dev_m = lock(vdev);
                    let _ = dev_m.emit(&[
                        InputEvent::new(EventType::RELATIVE, RelativeAxisType::REL_X.0, dx),
                        InputEvent::new(EventType::RELATIVE, RelativeAxisType::REL_Y.0, dy),
                        InputEvent::new(EventType::SYNCHRONIZATION, 0, 0),
                    ]);
                }
                continue;
            }
            ActionType::MOUSE_SCROLL => {
                let delta = action.scroll_delta.unwrap_or(0);
                let _ = dev.emit(&[
                    InputEvent::new(EventType::RELATIVE, RelativeAxisType::REL_WHEEL.0, delta),
                    InputEvent::new(EventType::SYNCHRONIZATION, 0, 0),
                ]);
            }
            ActionType::TEXT => {
                if let Some(txt) = &action.text {
                    drop(dev);
                    drop(pressed);
                    for ch in txt.chars() {
                        if PANIC_STOP.load(Ordering::SeqCst)
                            || stop_flag.is_some_and(|f| !f.load(Ordering::SeqCst))
                        {
                            let mut d = lock(vdev);
                            let mut p = lock(pressed_keys);
                            release_all_keys(&mut d, &mut p);
                            return false;
                        }
                        if let Some((key, with_shift)) = char_to_evdev_key(ch) {
                            let mut dev_c = lock(vdev);
                            if with_shift {
                                emit_key(&mut dev_c, Key::KEY_LEFTSHIFT, 1);
                                // İzlenen sete eklenmezse iptal/STOP anında Shift takılı kalır.
                                lock(pressed_keys).insert(Key::KEY_LEFTSHIFT);
                                drop(dev_c);
                                if !cancellable_sleep(8, 0, stop_flag) {
                                    let mut d = lock(vdev);
                                    let mut p = lock(pressed_keys);
                                    release_all_keys(&mut d, &mut p);
                                    return false;
                                }
                                dev_c = lock(vdev);
                            }
                            emit_key(&mut dev_c, key, 1);
                            drop(dev_c);
                            if !cancellable_sleep(16, 0, stop_flag) {
                                let mut d = lock(vdev);
                                let mut p = lock(pressed_keys);
                                release_all_keys(&mut d, &mut p);
                                return false;
                            }
                            let mut dev_c2 = lock(vdev);
                            emit_key(&mut dev_c2, key, 0);
                            if with_shift {
                                drop(dev_c2);
                                if !cancellable_sleep(8, 0, stop_flag) {
                                    let mut d = lock(vdev);
                                    let mut p = lock(pressed_keys);
                                    release_all_keys(&mut d, &mut p);
                                    return false;
                                }
                                dev_c2 = lock(vdev);
                                emit_key(&mut dev_c2, Key::KEY_LEFTSHIFT, 0);
                                lock(pressed_keys).remove(&Key::KEY_LEFTSHIFT);
                            }
                            drop(dev_c2);
                            if !cancellable_sleep(16, 0, stop_flag) {
                                let mut d = lock(vdev);
                                let mut p = lock(pressed_keys);
                                release_all_keys(&mut d, &mut p);
                                return false;
                            }
                        } else {
                            warn_unsupported_char(ch);
                        }
                    }
                    continue;
                }
            }
            ActionType::DELAY => {
                let ms = action.delay_ms.unwrap_or(20);
                let jitter = action.jitter_ms.unwrap_or(0);
                drop(dev);
                drop(pressed);
                if !cancellable_sleep(ms, jitter, stop_flag) {
                    let mut d = lock(vdev);
                    let mut p = lock(pressed_keys);
                    release_all_keys(&mut d, &mut p);
                    return false;
                }
                continue;
            }
        }

        drop(dev);
        drop(pressed);
    }
    true
}

fn discover_devices(verbose: bool) -> (Vec<evdev::Device>, usize) {
    let mut devices = Vec::new();
    let mut permission_denied = 0;

    if let Ok(entries) = fs::read_dir("/dev/input") {
        for entry in entries.flatten() {
            let path = entry.path();
            if let Some(file_name) = path.file_name().and_then(|f| f.to_str()) {
                if file_name.starts_with("event") {
                    match evdev::Device::open(&path) {
                        Ok(dev) => {
                            if let Some(name) = dev.name() {
                                if name.contains("MacroStat")
                                    || name.contains("CachyMacro")
                                    || name.contains("Virtual Engine")
                                {
                                    continue;
                                }
                            }
                            let is_input = if let Some(keys) = dev.supported_keys() {
                                keys.iter().count() > 0
                            } else {
                                false
                            };

                            if is_input {
                                if verbose {
                                    println!(
                                        " -> [Aygıt Bağlandı] {} ({})",
                                        dev.name().unwrap_or("Giriş Aygıtı"),
                                        path.display()
                                    );
                                }
                                devices.push(dev);
                            }
                        }
                        Err(e) => {
                            if e.kind() == std::io::ErrorKind::PermissionDenied {
                                permission_denied += 1;
                            }
                        }
                    }
                }
            }
        }
    }
    (devices, permission_denied)
}

/// Göreli X/Y ekseni sunan fiziksel işaretçi aygıtlarını bulur (fare, dokunmatik
/// yüzey). Sanal MacroStat aygıtları kayda alınmaz; aksi hâlde geri besleme olur.
fn discover_pointer_devices() -> (Vec<evdev::Device>, usize) {
    let mut devices = Vec::new();
    let mut permission_denied = 0;

    if let Ok(entries) = fs::read_dir("/dev/input") {
        for entry in entries.flatten() {
            let path = entry.path();
            let Some(file_name) = path.file_name().and_then(|f| f.to_str()) else {
                continue;
            };
            if !file_name.starts_with("event") {
                continue;
            }
            match evdev::Device::open(&path) {
                Ok(dev) => {
                    if let Some(name) = dev.name() {
                        if name.contains("MacroStat")
                            || name.contains("CachyMacro")
                            || name.contains("Virtual Engine")
                        {
                            continue;
                        }
                    }
                    let has_xy = dev.supported_relative_axes().is_some_and(|axes| {
                        axes.contains(RelativeAxisType::REL_X)
                            && axes.contains(RelativeAxisType::REL_Y)
                    });
                    if has_xy {
                        println!(
                            "[KAYIT] İşaretçi aygıtı: {} ({})",
                            dev.name().unwrap_or("Giriş Aygıtı"),
                            path.display()
                        );
                        devices.push(dev);
                    }
                }
                Err(e) => {
                    if e.kind() == std::io::ErrorKind::PermissionDenied {
                        permission_denied += 1;
                    }
                }
            }
        }
    }
    (devices, permission_denied)
}

#[derive(Serialize)]
struct MousePathRecording {
    version: u32,
    sample_ms: u64,
    duration_ms: u64,
    points: Vec<[i64; 3]>,
    /// (kayıt başından itibaren ms, "BTN_*", 1 = basıldı / 0 = bırakıldı)
    #[serde(skip_serializing_if = "Vec::is_empty", default)]
    buttons: Vec<(i64, String, i32)>,
    #[serde(skip_serializing_if = "Option::is_none")]
    start: Option<[i32; 2]>,
}

/// Kayda alınan fiziksel fare düğmesi kodunu motor adına çevirir.
fn mouse_button_name(code: u16) -> Option<&'static str> {
    match code {
        c if c == Key::BTN_LEFT.0 => Some("BTN_LEFT"),
        c if c == Key::BTN_RIGHT.0 => Some("BTN_RIGHT"),
        c if c == Key::BTN_MIDDLE.0 => Some("BTN_MIDDLE"),
        c if c == Key::BTN_SIDE.0 => Some("BTN_SIDE"),
        c if c == Key::BTN_EXTRA.0 => Some("BTN_EXTRA"),
        _ => None,
    }
}

fn write_mouse_recording(path: &Path, recording: &MousePathRecording) -> std::io::Result<()> {
    use std::io::Write;
    use std::os::unix::fs::OpenOptionsExt;

    let data = serde_json::to_vec(recording)?;
    let tmp = path.with_extension("tmp");
    {
        let mut file = fs::OpenOptions::new()
            .create(true)
            .truncate(true)
            .write(true)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW)
            .open(&tmp)?;
        file.write_all(&data)?;
        file.sync_all()?;
    }
    fs::rename(&tmp, path)?;
    Ok(())
}

/// `--record-mouse <dosya>`: sistem genelindeki göreli fare hareketini kaydeder.
/// Kilit ve uinput kullanmaz; yalnızca /dev/input okur. STOP tuşu, SIGTERM veya
/// sınırlar dolduğunda birleştirilmiş yolu atomik olarak yazar.
fn run_record_mouse(
    output: &Path,
    panic_key: Key,
    panic_key_name: &str,
    start_override: Option<[i32; 2]>,
) -> i32 {
    // X11'de kaydın başladığı imleç konumu okunabilir; oynatma bu noktaya
    // hizalanır. Wayland'da konum arayüz tarafından KWin betiğiyle okunup
    // `start_override` olarak verilir; okunamadıysa alan yazılmaz.
    let start = start_override.or_else(|| x11::pointer_position().map(|(x, y)| [x, y]));
    let (mut devices, permission_denied) = discover_pointer_devices();
    if devices.is_empty() {
        if permission_denied > 0 {
            eprintln!("[HATA: İZİN GEREKLİ] /dev/input/event* aygıtlarına okuma izni verilemedi.");
        } else {
            eprintln!("[HATA] Göreli X/Y ekseni sunan işaretçi aygıtı bulunamadı.");
        }
        return 2;
    }

    let mut poll_fds: Vec<libc::pollfd> = devices
        .iter()
        .map(|d| libc::pollfd {
            fd: d.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        })
        .collect();

    println!(
        "[KAYIT] Fare hareketi kaydediliyor; durdurmak için {} veya arayüzdeki düğme.",
        panic_key_name
    );
    println!("[KAYIT] Çıktı: {}", output.display());
    if let Some([x, y]) = start {
        println!("[KAYIT] Başlangıç imleç konumu: ({x}, {y})");
    }

    let started = Instant::now();
    let mut last_emit = started;
    let mut acc_dx: i64 = 0;
    let mut acc_dy: i64 = 0;
    let mut points: Vec<[i64; 3]> = Vec::new();
    let mut buttons: Vec<(i64, String, i32)> = Vec::new();
    let mut interrupted = false;

    loop {
        if SHUTDOWN.load(Ordering::SeqCst) {
            break;
        }

        let ret = unsafe { libc::poll(poll_fds.as_mut_ptr(), poll_fds.len() as libc::nfds_t, 20) };
        if ret < 0 {
            let err = std::io::Error::last_os_error();
            if err.raw_os_error() == Some(libc::EINTR) {
                continue;
            }
            thread::sleep(Duration::from_millis(20));
        } else if ret > 0 {
            // Aygıt kaybolursa poll sürekli hata döndürür; POLLIN yoksa
            // döngüyü bırakıp kaydı bitir (aksi hâlde CPU meşgul döner).
            if poll_fds.iter().all(|pfd| pfd.revents & libc::POLLIN == 0) {
                break;
            }
            for (i, pfd) in poll_fds.iter().enumerate() {
                if pfd.revents & libc::POLLIN == 0 {
                    continue;
                }
                if let Ok(events) = devices[i].fetch_events() {
                    for ev in events {
                        match ev.event_type() {
                            EventType::RELATIVE => {
                                if ev.code() == RelativeAxisType::REL_X.0 {
                                    acc_dx += i64::from(ev.value());
                                } else if ev.code() == RelativeAxisType::REL_Y.0 {
                                    acc_dy += i64::from(ev.value());
                                }
                            }
                            EventType::KEY if ev.value() == 1 && ev.code() == panic_key.0 => {
                                println!("[KAYIT] STOP tuşuna basıldı; kayıt bitiriliyor.");
                                interrupted = true;
                            }
                            EventType::KEY if ev.value() == 0 || ev.value() == 1 => {
                                if let Some(name) = mouse_button_name(ev.code()) {
                                    buttons.push((
                                        started.elapsed().as_millis().min(i64::MAX as u128) as i64,
                                        name.to_string(),
                                        ev.value(),
                                    ));
                                }
                            }
                            _ => {}
                        }
                    }
                }
            }
        }

        if interrupted {
            break;
        }

        // Olayları 4 ms'lik dilimlerde birleştir; duruş boşlukları dt olarak korunur.
        let elapsed = last_emit.elapsed();
        if elapsed >= Duration::from_millis(MOUSE_RECORD_SAMPLE_MS) && (acc_dx != 0 || acc_dy != 0)
        {
            points.push([
                elapsed.as_millis().min(i64::MAX as u128) as i64,
                acc_dx.clamp(i32::MIN as i64, i32::MAX as i64),
                acc_dy.clamp(i32::MIN as i64, i32::MAX as i64),
            ]);
            acc_dx = 0;
            acc_dy = 0;
            last_emit = Instant::now();
        }

        if points.len() >= MAX_MOUSE_PATH_POINTS {
            eprintln!(
                "[KAYIT] Nokta sınırına ulaşıldı ({}); kayıt bitiriliyor.",
                MAX_MOUSE_PATH_POINTS
            );
            break;
        }
        if started.elapsed() >= Duration::from_secs(MOUSE_RECORD_MAX_SECS) {
            eprintln!(
                "[KAYIT] Süre sınırına ulaşıldı ({} sn); kayıt bitiriliyor.",
                MOUSE_RECORD_MAX_SECS
            );
            break;
        }
    }

    if acc_dx != 0 || acc_dy != 0 {
        points.push([
            last_emit.elapsed().as_millis().min(i64::MAX as u128) as i64,
            acc_dx.clamp(i32::MIN as i64, i32::MAX as i64),
            acc_dy.clamp(i32::MIN as i64, i32::MAX as i64),
        ]);
    }

    let recording = MousePathRecording {
        version: 1,
        sample_ms: MOUSE_RECORD_SAMPLE_MS,
        duration_ms: started.elapsed().as_millis().min(u64::MAX as u128) as u64,
        points,
        buttons,
        start,
    };
    match write_mouse_recording(output, &recording) {
        Ok(()) => {
            println!(
                "[KAYIT] {} nokta, {} ms kaydedildi → {}",
                recording.points.len(),
                recording.duration_ms,
                output.display()
            );
            0
        }
        Err(e) => {
            eprintln!("[HATA] Kayıt yazılamadı ({}): {}", output.display(), e);
            4
        }
    }
}

/// STOP sonrası arayüz bu süreci başlatır: yalnızca yeniden başlatma tuşunu
/// dinler. Kilit ve uinput kullanmaz; tuşa basılınca `[RESTART]` yazıp özel
/// çıkış koduyla sonlanır, böylece arayüz motoru yeniden başlatabilir.
fn run_watch_restart(key: Key, key_name: &str) -> i32 {
    let (mut devices, permission_denied) = discover_devices(false);
    if devices.is_empty() {
        if permission_denied > 0 {
            eprintln!("[HATA: İZİN GEREKLİ] /dev/input/event* aygıtlarına okuma izni verilemedi.");
        } else {
            eprintln!("[HATA] Dinlenecek giriş aygıtı bulunamadı.");
        }
        return 2;
    }

    let mut poll_fds: Vec<libc::pollfd> = devices
        .iter()
        .map(|d| libc::pollfd {
            fd: d.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        })
        .collect();

    println!("[BEKLE] STOP sonrası yeniden başlatma tuşu dinleniyor: {key_name}");

    while !SHUTDOWN.load(Ordering::SeqCst) {
        let ret = unsafe { libc::poll(poll_fds.as_mut_ptr(), poll_fds.len() as libc::nfds_t, 50) };
        if ret < 0 {
            let err = std::io::Error::last_os_error();
            if err.raw_os_error() == Some(libc::EINTR) {
                continue;
            }
            thread::sleep(Duration::from_millis(50));
            continue;
        }
        if ret == 0 {
            continue;
        }
        // Tüm aygıtlar hata/askıda ise izleme sürdürülemez; temiz çık.
        if poll_fds.iter().all(|pfd| pfd.revents & libc::POLLIN == 0) {
            return 0;
        }
        for (i, pfd) in poll_fds.iter().enumerate() {
            if pfd.revents & libc::POLLIN == 0 {
                continue;
            }
            if let Ok(events) = devices[i].fetch_events() {
                for ev in events {
                    if ev.event_type() == EventType::KEY && ev.value() == 1 && ev.code() == key.0 {
                        println!("[RESTART] {key_name} tuşuna basıldı.");
                        return WATCH_RESTART_EXIT_CODE;
                    }
                }
            }
        }
    }
    0
}

/// Komut satırı seçenekleri; `main` yalnızca bu yapıya bakar.
#[derive(Default)]
struct CliArgs {
    test_macro: Option<String>,
    record_mouse: Option<String>,
    panic_key: Option<String>,
    start_x: Option<i32>,
    start_y: Option<i32>,
    watch_restart_key: Option<String>,
    config: Option<String>,
}

fn parse_cli_args(raw: &[String]) -> CliArgs {
    let mut parsed = CliArgs::default();
    let mut args_iter = raw.iter().skip(1);
    while let Some(arg) = args_iter.next() {
        match arg.as_str() {
            "--test-macro" => parsed.test_macro = args_iter.next().cloned(),
            "--record-mouse" => parsed.record_mouse = args_iter.next().cloned(),
            "--panic-key" => parsed.panic_key = args_iter.next().cloned(),
            "--start-x" => parsed.start_x = args_iter.next().and_then(|v| v.parse().ok()),
            "--start-y" => parsed.start_y = args_iter.next().and_then(|v| v.parse().ok()),
            "--watch-restart" => parsed.watch_restart_key = args_iter.next().cloned(),
            other if !other.starts_with("--") => parsed.config = Some(other.to_string()),
            _ => {}
        }
    }
    parsed
}

/// /dev/input dizinini inotify ile izler; başarısız olursa -1 döner.
fn setup_input_watch() -> libc::c_int {
    unsafe {
        let fd = libc::inotify_init1(libc::IN_NONBLOCK | libc::IN_CLOEXEC);
        if fd < 0 {
            eprintln!("[UYARI] inotify başlatılamadı; aygıtlar 4 sn'de bir yoklanacak.");
            return -1;
        }
        let path = std::ffi::CString::new("/dev/input").unwrap();
        let wd = libc::inotify_add_watch(
            fd,
            path.as_ptr(),
            libc::IN_CREATE
                | libc::IN_DELETE
                | libc::IN_ATTRIB
                | libc::IN_MOVED_TO
                | libc::IN_MOVED_FROM,
        );
        if wd < 0 {
            eprintln!("[UYARI] /dev/input izlenemiyor; aygıtlar 4 sn'de bir yoklanacak.");
            libc::close(fd);
            return -1;
        }
        fd
    }
}

/// Bekleyen inotify olaylarını tüketir; en az bir olay varsa true döner.
fn drain_input_watch(fd: libc::c_int) -> bool {
    if fd < 0 {
        return false;
    }
    let mut buf = [0u8; 4096];
    let mut got = false;
    loop {
        let n = unsafe { libc::read(fd, buf.as_mut_ptr().cast(), buf.len()) };
        if n > 0 {
            got = true;
            continue;
        }
        // EAGAIN/EWOULDBLOCK: kuyruk boş. EINTR: olaylar kuyrukta kaldı, sonraki turda alınır.
        break;
    }
    got
}

// ---------------------------------------------------------------------------
// Profil, sinyal ve süreç yönetimi yardımcıları
// ---------------------------------------------------------------------------

/// Depoya gömülü tek varsayılan profil kaynağı (release derlemesinde sabitlenir).
const DEFAULT_PROFILE_JSON: &str = include_str!("../assets/default_profile.json");

extern "C" fn handle_termination(_signal: libc::c_int) {
    // Sinyal işleyicisi yalnızca atomik bayrak yazar; temizlik ana döngüde yapılır.
    SHUTDOWN.store(true, Ordering::SeqCst);
}

extern "C" fn handle_reload(_signal: libc::c_int) {
    RELOAD.store(true, Ordering::SeqCst);
}

/// Kilit dosyasının gerçekten bu kullanıcıya ait olduğunu doğrular.
///
/// Paylaşılan `/tmp` dizininde başka bir kullanıcı aynı adı önceden
/// oluşturabilir; böyle bir dosya kilit olarak kullanılmaz.
fn lock_file_owned_by(file: &fs::File, uid: u32) -> bool {
    use std::os::unix::fs::MetadataExt;
    file.metadata()
        .map(|meta| meta.uid() == uid)
        .unwrap_or(false)
}

/// Aynı kullanıcı için ikinci bir motorun başlamasını engeller.
/// Kilit süreç yaşadığı sürece tutulur; süreç ölünce kernel kilidi bırakır.
fn acquire_single_instance_lock() -> Option<fs::File> {
    use std::os::unix::fs::OpenOptionsExt;

    let uid = unsafe { libc::getuid() };
    let candidates = [
        format!("/run/user/{}/macrostat.lock", uid),
        format!("/tmp/macrostat-{}.lock", uid),
    ];
    for path in candidates {
        match fs::OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW)
            .open(&path)
        {
            Ok(file) => {
                if !lock_file_owned_by(&file, uid) {
                    eprintln!(
                        "[UYARI] Kilit dosyası bu kullanıcıya ait değil ({}), atlandı.",
                        path
                    );
                    continue;
                }
                let rc = unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) };
                if rc == 0 {
                    return Some(file);
                }
                eprintln!(
                    "[HATA] Başka bir MacroStat motoru zaten çalışıyor (kilit: {}).",
                    path
                );
                std::process::exit(3);
            }
            Err(e) => {
                eprintln!("[UYARI] Kilit dosyası açılamadı ({}): {}", path, e);
            }
        }
    }
    eprintln!("[UYARI] Tek örnek kilidi oluşturulamadı; motor yine de başlatılıyor.");
    None
}

/// Çoklu profil sarmalayıcısını veya eski tekil profili tek noktadan çözer.
fn parse_profile(contents: &str) -> Option<ProfileConfig> {
    if let Ok(wrapper) = serde_json::from_str::<MultiProfileWrapper>(contents) {
        if !wrapper.profiles.is_empty() {
            let active_id = wrapper.active_profile_id.clone().unwrap_or_default();
            let selected = wrapper
                .profiles
                .iter()
                .find(|p| p.id == active_id)
                .cloned()
                .unwrap_or_else(|| wrapper.profiles[0].clone());
            println!(
                "[BAŞARILI] Çoklu profil yapılandırması yüklendi ({} profil). Aktif: '{}'",
                wrapper.profiles.len(),
                selected.name
            );
            return Some(selected);
        }
    }
    serde_json::from_str::<ProfileConfig>(contents).ok()
}

fn default_profile() -> ProfileConfig {
    parse_profile(DEFAULT_PROFILE_JSON).unwrap_or_else(|| ProfileConfig {
        id: "profile-cachy-default".to_string(),
        name: "MacroStat Varsayılan Profil".to_string(),
        panic_key: "KEY_PAUSE".to_string(),
        virtual_device_name: "MacroStat Virtual Engine".to_string(),
        macros: Vec::new(),
    })
}

/// Sol/sağ varyantlarını aynı fiziksel tuş sınıfına indirger (çift dokunma izleme).
fn canonical_key_id(key: Key) -> u16 {
    if key == Key::KEY_LEFTCTRL || key == Key::KEY_RIGHTCTRL {
        Key::KEY_LEFTCTRL.0
    } else if key == Key::KEY_LEFTSHIFT || key == Key::KEY_RIGHTSHIFT {
        Key::KEY_LEFTSHIFT.0
    } else if key == Key::KEY_LEFTALT || key == Key::KEY_RIGHTALT {
        Key::KEY_LEFTALT.0
    } else if key == Key::KEY_LEFTMETA || key == Key::KEY_RIGHTMETA {
        Key::KEY_LEFTMETA.0
    } else {
        key.0
    }
}

/// Her tuş olayında yeniden ayrıştırma yapmamak için tetikleyiciler açılışta derlenir.
struct CompiledMacro {
    id: String,
    name: String,
    trigger_key: String,
    mode: TriggerMode,
    single: Option<Key>,
    combo: Vec<Key>,
    repeat_count: u32,
    double_tap_ms: u64,
    hold_ms: u64,
    action_index: usize,
}

/// stderr düzenli bir dosyaya yönlendirilmişse ve sınırı aştıysa dosyayı kırpar.
/// GUI günlüğü açılışta döndürür; uzun süre açık kalan motor da kendi kendine kırpar.
fn maybe_rotate_stderr_log(max_bytes: u64) {
    unsafe {
        let mut st: libc::stat = std::mem::zeroed();
        if libc::fstat(libc::STDERR_FILENO, &mut st) != 0 {
            return;
        }
        if (st.st_mode & libc::S_IFMT) != libc::S_IFREG {
            return;
        }
        if st.st_size <= 0 || (st.st_size as u64) <= max_bytes {
            return;
        }
        // O_APPEND ile açılmış fd olduğu için sonraki yazılar yeni dosya sonuna gider.
        libc::ftruncate(libc::STDERR_FILENO, 0);
        println!("[GÜNLÜK] Boyut sınırı aşıldı; günlük dosyası sıfırlandı.");
    }
}

fn compile_macros(profile: &ProfileConfig) -> Vec<CompiledMacro> {
    let mut compiled = Vec::new();
    for (index, m) in profile.macros.iter().enumerate() {
        if !m.enabled {
            continue;
        }
        let parts: Vec<&str> = m
            .trigger_key
            .split('+')
            .map(str::trim)
            .filter(|part| !part.is_empty())
            .collect();
        let keys: Vec<Key> = parts
            .iter()
            .filter_map(|part| string_to_key(part))
            .collect();
        if keys.is_empty() || keys.len() != parts.len() {
            eprintln!(
                "[UYARI] Geçersiz tetikleyici '{}' (makro: '{}'), atlandı.",
                m.trigger_key, m.name
            );
            continue;
        }
        let id = if m.id.is_empty() {
            format!("idx-{}", index)
        } else {
            format!("{}#{}", m.id, index)
        };
        compiled.push(CompiledMacro {
            id,
            name: m.name.clone(),
            trigger_key: m.trigger_key.clone(),
            mode: m.trigger_mode.clone(),
            single: if keys.len() == 1 { Some(keys[0]) } else { None },
            combo: if keys.len() > 1 { keys } else { Vec::new() },
            repeat_count: m.repeat_count.max(1),
            double_tap_ms: m.double_tap_timeout_ms.max(1),
            hold_ms: m.hold_duration_ms.max(1),
            action_index: index,
        });
    }
    compiled
}

fn trigger_matches(m: &CompiledMacro, key: Key, is_press: bool, held: &HashSet<Key>) -> bool {
    if !is_press {
        return false;
    }
    if let Some(single) = m.single {
        keys_are_equivalent(single, key)
    } else {
        m.combo.iter().any(|k| keys_are_equivalent(*k, key))
            && m.combo
                .iter()
                .all(|k| held.iter().any(|h| keys_are_equivalent(*k, *h)))
    }
}

/// Profil dosyası için üst sınır. Elle düzenlenen ya da bozulmuş bir dosyanın
/// belleği tüketmesini engeller; gerçek profiller birkaç yüz kilobayttır.
const MAX_PROFILE_BYTES: u64 = 32 * 1024 * 1024;

/// Profil dosyasını son bileşendeki sembolik bağlantıları izlemeden açar.
///
/// Profil kullanıcı denetimindedir; `O_NOFOLLOW` başka bir dosyaya yönlenen
/// bağlantı üzerinden okuma yapılmasını engeller.
fn open_private_profile(path: &Path) -> std::io::Result<fs::File> {
    use std::ffi::CString;
    use std::io::{Error, ErrorKind};
    use std::os::unix::ffi::OsStrExt;
    use std::os::unix::io::FromRawFd;

    let c_path = CString::new(path.as_os_str().as_bytes())
        .map_err(|_| Error::new(ErrorKind::InvalidInput, "profil yolu geçersiz"))?;
    // SAFETY: `c_path` NUL ile sonlandırılmış ve çağrı boyunca yaşıyor;
    // dönen geçerli fd başarıda `File` tarafından sahiplenilir.
    let fd = unsafe {
        libc::open(
            c_path.as_ptr(),
            libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NOFOLLOW,
        )
    };
    if fd < 0 {
        return Err(Error::last_os_error());
    }
    // SAFETY: fd yukarıda başarıyla açıldı ve başka hiçbir sahip yok.
    Ok(unsafe { fs::File::from_raw_fd(fd) })
}

/// `path` dosyasını en fazla `limit` bayt okuyup UTF-8 metne çevirir.
///
/// Sınır aşılırsa `InvalidData` döner; dosyanın tamamı belleğe alınmaz.
fn read_profile_text(path: &Path, limit: u64) -> std::io::Result<String> {
    use std::io::{Error, ErrorKind, Read};
    let file = open_private_profile(path)?;
    if file.metadata()?.len() > limit {
        return Err(Error::new(
            ErrorKind::InvalidData,
            "profil dosyası çok büyük",
        ));
    }
    let mut contents = String::new();
    file.take(limit + 1).read_to_string(&mut contents)?;
    if contents.len() as u64 > limit {
        return Err(Error::new(
            ErrorKind::InvalidData,
            "profil dosyası çok büyük",
        ));
    }
    Ok(contents)
}

fn load_profile_file(config_path: &Path) -> ProfileConfig {
    if config_path.exists() {
        println!(
            "[BİLGİ] Yapılandırma dosyası okunuyor: {}",
            config_path.display()
        );
        match read_profile_text(config_path, MAX_PROFILE_BYTES) {
            Ok(contents) => match parse_profile(&contents) {
                Some(p) => p,
                None => {
                    eprintln!(
                        "[UYARI] {} ayrıştırılamadı. Varsayılan profil kullanılıyor.",
                        config_path.display()
                    );
                    default_profile()
                }
            },
            Err(e) => {
                eprintln!(
                    "[UYARI] {} okunamadı: {}. Varsayılan profil kullanılıyor.",
                    config_path.display(),
                    e
                );
                default_profile()
            }
        }
    } else {
        println!(
            "[BİLGİ] {} bulunamadı, varsayılan profil yükleniyor.",
            config_path.display()
        );
        default_profile()
    }
}

/// `--test-macro <id>`: arayüzün "Makroyu Test Et" düğmesi için tek seferlik
/// çalıştırma. Kilit alınmaz, fiziksel aygıtlar dinlenmez; yalnızca eylemler
/// geçici bir sanal aygıt üzerinden icra edilir.
fn run_test_macro(profile: &ProfileConfig, macro_id: &str) -> i32 {
    if fs::OpenOptions::new()
        .write(true)
        .open("/dev/uinput")
        .is_err()
    {
        eprintln!(
            "[HATA] /dev/uinput yazılabilir değil. Arayüzdeki 'İzinleri Düzelt' düğmesini kullanın."
        );
        return 2;
    }

    let Some(m) = profile
        .macros
        .iter()
        .find(|m| m.id == macro_id || m.name == macro_id)
    else {
        eprintln!("[HATA] Test edilecek makro bulunamadı: {}", macro_id);
        return 3;
    };

    let mut actions = m.actions.clone();
    actions.extend(m.release_actions.iter().cloned());
    if actions.is_empty() {
        eprintln!("[HATA] '{}' makrosunda eylem yok.", m.name);
        return 4;
    }

    println!(
        "[TEST] '{}' makrosu çalıştırılıyor ({} eylem).",
        m.name,
        actions.len()
    );
    let vdev = Arc::new(Mutex::new(create_virtual_device("MacroStat Test Engine")));
    let pressed = Arc::new(Mutex::new(HashSet::new()));
    let completed = execute_macro_actions(&actions, &vdev, &pressed, None);
    {
        let mut dev = lock(&vdev);
        let mut keys = lock(&pressed);
        release_all_keys(&mut dev, &mut keys);
    }
    if completed {
        println!("[TEST] Tamamlandı.");
        0
    } else {
        eprintln!("[TEST] Test iptal edildi.");
        5
    }
}

fn main() {
    // Linux PR_SET_PDEATHSIG: Ana GUI kapandığında kernel bu motoru SIGTERM ile uyarır.
    unsafe {
        libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGTERM);
        // SIGTERM/SIGINT temiz kapanışa dönüştürülür; basılı tuşlar serbest bırakılır.
        libc::signal(
            libc::SIGTERM,
            handle_termination as extern "C" fn(libc::c_int) as libc::sighandler_t,
        );
        libc::signal(
            libc::SIGINT,
            handle_termination as extern "C" fn(libc::c_int) as libc::sighandler_t,
        );
        // SIGUSR1: profili yeniden başlatmadan tazele.
        libc::signal(
            libc::SIGUSR1,
            handle_reload as extern "C" fn(libc::c_int) as libc::sighandler_t,
        );
    }

    if unsafe { libc::getppid() } == 1 {
        eprintln!("[HATA] Ana süreç bulunamadı; motor başlatılmadı.");
        std::process::exit(0);
    }

    // Argümanlar: [--test-macro <id>] [--record-mouse <dosya>]
    //            [--watch-restart <KEY_*>] [--panic-key <KEY_*>]
    //            [--start-x <px> --start-y <px>] [profil.json]
    let raw_args: Vec<String> = std::env::args().collect();
    let cli = parse_cli_args(&raw_args);

    // Yeniden başlatma izleyicisi: profil, kilit veya uinput gerektirmez.
    if let Some(key_arg) = &cli.watch_restart_key {
        let key = string_to_key(key_arg).unwrap_or(Key::KEY_F12);
        let name = if string_to_key(key_arg).is_some() {
            key_arg.to_uppercase()
        } else {
            String::from("KEY_F12")
        };
        std::process::exit(run_watch_restart(key, &name));
    }

    // Kayıt modu profil, kilit veya uinput gerektirmez.
    if let Some(output) = &cli.record_mouse {
        let (panic_key, panic_key_name) = match cli.panic_key.as_deref().and_then(string_to_key) {
            Some(key) => (key, cli.panic_key.clone().unwrap_or_default()),
            None => (Key::KEY_PAUSE, String::from("KEY_PAUSE")),
        };
        let start_override = match (cli.start_x, cli.start_y) {
            (Some(x), Some(y)) => Some([
                x.clamp(-1_000_000, 1_000_000),
                y.clamp(-1_000_000, 1_000_000),
            ]),
            _ => None,
        };
        std::process::exit(run_record_mouse(
            Path::new(output),
            panic_key,
            &panic_key_name,
            start_override,
        ));
    }
    let config_path = cli
        .config
        .map(std::path::PathBuf::from)
        .filter(|path| path.exists())
        .or_else(|| {
            std::env::var_os("CACHYMACRO_PROFILE")
                .map(std::path::PathBuf::from)
                .filter(|path| path.exists())
        })
        .unwrap_or_else(|| std::path::PathBuf::from("profile.json"));

    let mut profile: ProfileConfig = load_profile_file(&config_path);

    // Test modu kilit/aygıt taraması yapmadan tek makroyu çalıştırır.
    if let Some(macro_id) = &cli.test_macro {
        std::process::exit(run_test_macro(&profile, macro_id));
    }

    // Kilit süreç boyunca tutulur (_lock_file kapsam dışına çıkmaz).
    let _lock_file = acquire_single_instance_lock();

    println!("=======================================================");
    println!("  MacroStat Daemon - Linux (CachyOS/KDE) Makro Motoru ");
    println!("  Wayland & X11 | Panic Switch: profil / KEY_PAUSE ");
    println!("=======================================================");

    println!("[HAZIR] Yüklenen Profil: {}", profile.name);
    for m in &profile.macros {
        println!(
            "  -> [{}] '{}' (Tetikleyici: {} | Mod: {:?})",
            if m.enabled { "AKTİF" } else { "KAPALI" },
            m.name,
            m.trigger_key,
            m.trigger_mode
        );
    }

    let mut compiled_macros = compile_macros(&profile);
    println!(
        "[HAZIR] {} etkin tetikleyici derlendi.",
        compiled_macros.len()
    );

    let virtual_device = create_virtual_device(&profile.virtual_device_name);
    let vdev_arc = Arc::new(Mutex::new(virtual_device));
    let pressed_keys_arc = Arc::new(Mutex::new(HashSet::new()));
    let physical_held_keys_arc: Arc<RwLock<HashSet<Key>>> = Arc::new(RwLock::new(HashSet::new()));
    let running_toggles: Arc<Mutex<HashMap<String, Arc<AtomicBool>>>> =
        Arc::new(Mutex::new(HashMap::new()));
    let double_tap_tracker: Arc<Mutex<HashMap<String, (Instant, u64)>>> =
        Arc::new(Mutex::new(HashMap::new()));

    let (mut devices, mut perm_denied) = discover_devices(true);
    while devices.is_empty() {
        if SHUTDOWN.load(Ordering::SeqCst) || unsafe { libc::getppid() } == 1 {
            return;
        }
        if perm_denied > 0 {
            eprintln!("[HATA: İZİN GEREKLİ] /dev/input/event* aygıtlarına okuma izni verilemedi.");
            eprintln!("Arayüzdeki 'Donanım İzinlerini Düzelt' butonuna tıklayın.");
        }
        thread::sleep(Duration::from_millis(1500));
        let (d, p) = discover_devices(false);
        devices = d;
        perm_denied = p;
    }

    let mut poll_fds: Vec<libc::pollfd> = devices
        .iter()
        .map(|d| libc::pollfd {
            fd: d.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        })
        .collect();

    let mut panic_key_val = string_to_key(&profile.panic_key).unwrap_or(Key::KEY_PAUSE);
    let inotify_fd = setup_input_watch();
    let mut last_scan = Instant::now();
    // Kombinasyon mandalı: tuşlardan biri bırakılmadan aynı kombinasyon tekrar ateşlenmez.
    let mut latched_combos: HashSet<String> = HashSet::new();
    // PRESS_AND_RELEASE makrolarında bırakış eylemlerinin bir kez çalışmasını sağlar.
    let mut press_release_armed: HashSet<String> = HashSet::new();
    let mut last_log_check = Instant::now();

    loop {
        if SHUTDOWN.load(Ordering::SeqCst) {
            println!("[MacroStat Motor] Kapanış sinyali alındı. Motor kapatılıyor.");
            break;
        }
        if last_log_check.elapsed() > Duration::from_secs(30) {
            last_log_check = Instant::now();
            maybe_rotate_stderr_log(1_000_000);
        }
        if unsafe { libc::getppid() } == 1 {
            println!("[MacroStat Motor] Ana uygulama sonlandırıldı. Motor kapatılıyor.");
            break;
        }

        // 3. GUI'den SIGUSR1 geldiyse profili yeniden başlatmadan tazele.
        if RELOAD.swap(false, Ordering::SeqCst) {
            match read_profile_text(&config_path, MAX_PROFILE_BYTES)
                .ok()
                .and_then(|c| parse_profile(&c))
            {
                Some(new_profile) => {
                    {
                        let toggles = lock(&running_toggles);
                        for flag in toggles.values() {
                            flag.store(false, Ordering::SeqCst);
                        }
                    }
                    lock(&running_toggles).clear();
                    {
                        let mut dev = lock(&vdev_arc);
                        let mut pressed = lock(&pressed_keys_arc);
                        release_all_keys(&mut dev, &mut pressed);
                    }
                    latched_combos.clear();
                    press_release_armed.clear();
                    lock(&double_tap_tracker).clear();

                    if new_profile.virtual_device_name != profile.virtual_device_name {
                        println!("[YENİLE] Sanal aygıt adı değişikliği bir sonraki motor başlatmasında uygulanacak.");
                    }
                    panic_key_val = string_to_key(&new_profile.panic_key).unwrap_or(Key::KEY_PAUSE);
                    compiled_macros = compile_macros(&new_profile);
                    println!(
                        "[YENİLE] Profil yeniden yüklendi: '{}' ({} etkin tetikleyici)",
                        new_profile.name,
                        compiled_macros.len()
                    );
                    profile = new_profile;
                }
                None => eprintln!("[YENİLE] Profil okunamadı; mevcut yapılandırma korunuyor."),
            }
        }

        let ret = unsafe { libc::poll(poll_fds.as_mut_ptr(), poll_fds.len() as libc::nfds_t, 200) };

        let has_err = poll_fds
            .iter()
            .any(|pfd| pfd.revents & (libc::POLLERR | libc::POLLHUP | libc::POLLNVAL) != 0);

        // Aygıt eklendi/çıkarıldı ya da bir fd bozuldu: listeyi yenile.
        // inotify yoksa geriye dönük olarak 4 sn'de bir yokla.
        let fallback_scan = inotify_fd < 0 && last_scan.elapsed() > Duration::from_secs(4);
        if drain_input_watch(inotify_fd) || has_err || fallback_scan {
            last_scan = Instant::now();
            devices = discover_devices(false).0;
            poll_fds = devices
                .iter()
                .map(|d| libc::pollfd {
                    fd: d.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                })
                .collect();
            continue;
        }

        if ret > 0 {
            for (i, pfd) in poll_fds.iter().enumerate() {
                if pfd.revents & libc::POLLIN == 0 {
                    continue;
                }
                if let Ok(events) = devices[i].fetch_events() {
                    for ev in events {
                        if ev.event_type() != EventType::KEY {
                            continue;
                        }
                        let key = Key::new(ev.code());
                        let is_press = ev.value() == 1;
                        let is_release = ev.value() == 0;

                        if is_press {
                            physical_held_keys_arc.write().unwrap().insert(key);
                        } else if is_release {
                            physical_held_keys_arc.write().unwrap().remove(&key);
                            // Bırakılan tuşu içeren kombinasyon mandalları açılır.
                            latched_combos.retain(|macro_id| {
                                compiled_macros
                                    .iter()
                                    .find(|m| &m.id == macro_id)
                                    .is_some_and(|m| {
                                        !m.combo.iter().any(|k| keys_are_equivalent(*k, key))
                                    })
                            });
                        }

                        if is_press && keys_are_equivalent(key, panic_key_val) {
                            println!(
                                "\n[STOP] Acil durdurma tetiklendi! Tüm makrolar sonlandırıldı."
                            );
                            PANIC_STOP.store(true, Ordering::SeqCst);
                            {
                                let mut toggles = lock(&running_toggles);
                                for flag in toggles.values() {
                                    flag.store(false, Ordering::SeqCst);
                                }
                                toggles.clear();
                            }
                            {
                                let mut dev = lock(&vdev_arc);
                                let mut pressed = lock(&pressed_keys_arc);
                                release_all_keys(&mut dev, &mut pressed);
                            }
                            println!("[STOP] Makro motoru durduruldu. Arayüzden yeniden başlatılana kadar makrolar çalışmayacaktır.");
                            std::process::exit(0);
                        }

                        if is_press {
                            let mut matches = Vec::new();
                            {
                                let held = physical_held_keys_arc.read().unwrap();
                                for m in &compiled_macros {
                                    if trigger_matches(m, key, is_press, &held) {
                                        matches.push(m);
                                    }
                                }
                            }

                            for m in matches {
                                if !m.combo.is_empty() && latched_combos.contains(&m.id) {
                                    continue;
                                }
                                if !m.combo.is_empty() {
                                    latched_combos.insert(m.id.clone());
                                }

                                let macro_config = &profile.macros[m.action_index];
                                let actions_clone = macro_config.actions.clone();
                                let vdev_clone = Arc::clone(&vdev_arc);
                                let pressed_clone = Arc::clone(&pressed_keys_arc);
                                let mode = m.mode.clone();
                                let is_repeat = mode == TriggerMode::REPEAT_COUNT;
                                let repeat = m.repeat_count;
                                let macro_name = m.name.clone();
                                let macro_id_key = m.id.clone();

                                println!(
                                    "[MacroStat Tetiklendi] '{}' yürütülüyor (Tetikleyici: {} | Mod: {:?})",
                                    macro_name, m.trigger_key, mode
                                );

                                match mode {
                                    TriggerMode::ONCE => {
                                        thread::spawn(move || {
                                            execute_macro_actions(
                                                &actions_clone,
                                                &vdev_clone,
                                                &pressed_clone,
                                                None,
                                            );
                                            println!(
                                                "[MacroStat Tamamlandı] '{}' başarıyla tamamlandı.",
                                                macro_name
                                            );
                                        });
                                    }
                                    TriggerMode::REPEAT_COUNT | TriggerMode::TOGGLE_LOOP => {
                                        let mut toggles = lock(&running_toggles);
                                        if let Some(flag) = toggles.get(&macro_id_key) {
                                            if flag.load(Ordering::SeqCst) {
                                                println!("[DÖNGÜ KAPATILDI] Tetikleyiciye tekrar basıldı, makro durduruldu: '{}'", macro_name);
                                                flag.store(false, Ordering::SeqCst);
                                                toggles.remove(&macro_id_key);
                                                drop(toggles);
                                                let mut dev = lock(&vdev_arc);
                                                let mut pressed = lock(&pressed_keys_arc);
                                                release_all_keys(&mut dev, &mut pressed);
                                                continue;
                                            }
                                        }
                                        let flag = Arc::new(AtomicBool::new(true));
                                        toggles.insert(macro_id_key.clone(), Arc::clone(&flag));
                                        drop(toggles);

                                        if is_repeat {
                                            println!("[MacroStat Tetiklendi] '{}' başlatıldı ({} Tekrar)", macro_name, repeat);
                                        } else {
                                            println!("[DÖNGÜ BAŞLATILDI] Makro: '{}'", macro_name);
                                        }

                                        let flag_clone = Arc::clone(&flag);
                                        let toggles_ref = Arc::clone(&running_toggles);
                                        let key_str = macro_id_key.clone();
                                        let vdev_c = Arc::clone(&vdev_clone);
                                        let pressed_c = Arc::clone(&pressed_keys_arc);

                                        thread::spawn(move || {
                                            let mut rep: u32 = 0;
                                            while flag_clone.load(Ordering::SeqCst)
                                                && !PANIC_STOP.load(Ordering::SeqCst)
                                                && !SHUTDOWN.load(Ordering::SeqCst)
                                            {
                                                if !execute_macro_actions(
                                                    &actions_clone,
                                                    &vdev_c,
                                                    &pressed_c,
                                                    Some(&flag_clone),
                                                ) {
                                                    break;
                                                }
                                                rep += 1;
                                                if is_repeat {
                                                    println!(
                                                        "[MacroStat Tekrar {}/{}] '{}'",
                                                        rep, repeat, macro_name
                                                    );
                                                    if rep >= repeat {
                                                        break;
                                                    }
                                                }
                                                if !cancellable_sleep(5, 0, Some(&flag_clone)) {
                                                    break;
                                                }
                                            }
                                            {
                                                let mut dev = lock(&vdev_c);
                                                let mut pressed = lock(&pressed_c);
                                                release_all_keys(&mut dev, &mut pressed);
                                            }
                                            {
                                                let mut t = lock(&toggles_ref);
                                                t.remove(&key_str);
                                            }
                                            if is_repeat {
                                                println!("[MacroStat Tamamlandı] '{}' tüm tekrarlar tamamlandı.", macro_name);
                                            } else {
                                                println!("[DÖNGÜ SONLANDI] '{}'", macro_name);
                                            }
                                        });
                                    }
                                    TriggerMode::WHILE_HELD => {
                                        let held_arc_clone = Arc::clone(&physical_held_keys_arc);
                                        let required_keys: Vec<Key> = if m.combo.is_empty() {
                                            m.single.into_iter().collect()
                                        } else {
                                            m.combo.clone()
                                        };
                                        let name_clone = macro_name.clone();
                                        let vdev_c = Arc::clone(&vdev_clone);
                                        let pressed_c = Arc::clone(&pressed_clone);
                                        let stop_flag = Arc::new(AtomicBool::new(true));
                                        let stop_flag_c = Arc::clone(&stop_flag);

                                        thread::spawn(move || {
                                            while !PANIC_STOP.load(Ordering::SeqCst)
                                                && !SHUTDOWN.load(Ordering::SeqCst)
                                                && stop_flag_c.load(Ordering::SeqCst)
                                            {
                                                {
                                                    let held = held_arc_clone.read().unwrap();
                                                    if !required_keys.iter().all(|k| {
                                                        held.iter()
                                                            .any(|h| keys_are_equivalent(*k, *h))
                                                    }) {
                                                        break;
                                                    }
                                                }
                                                if !execute_macro_actions(
                                                    &actions_clone,
                                                    &vdev_c,
                                                    &pressed_c,
                                                    Some(&stop_flag_c),
                                                ) {
                                                    break;
                                                }
                                                if !cancellable_sleep(5, 0, Some(&stop_flag_c)) {
                                                    break;
                                                }
                                            }
                                            {
                                                let mut dev = lock(&vdev_c);
                                                let mut pressed = lock(&pressed_c);
                                                release_all_keys(&mut dev, &mut pressed);
                                            }
                                            println!(
                                                "[BASILI TUTMA BIRAKILDI] '{}' durduruldu.",
                                                name_clone
                                            );
                                        });
                                    }
                                    TriggerMode::DOUBLE_TAP => {
                                        let now = Instant::now();
                                        let tracker_key =
                                            format!("{}:{}", m.id, canonical_key_id(key));
                                        let mut tracker = lock(&double_tap_tracker);
                                        // Eski kayıtlar birikmesin; saklama süresi makronun penceresinden kısa olamaz.
                                        tracker.retain(|_, (t, window_ms)| {
                                            t.elapsed()
                                                < Duration::from_secs(5)
                                                    .max(Duration::from_millis(*window_ms))
                                        });
                                        let is_double =
                                            tracker.get(&tracker_key).is_some_and(|(last, _)| {
                                                last.elapsed()
                                                    <= Duration::from_millis(m.double_tap_ms)
                                            });

                                        if is_double {
                                            tracker.remove(&tracker_key);
                                            drop(tracker);
                                            println!(
                                                "[ÇİFT DOKUNMA] '{}' yürütülüyor (Pencere: {}ms)",
                                                macro_name, m.double_tap_ms
                                            );
                                            thread::spawn(move || {
                                                execute_macro_actions(
                                                    &actions_clone,
                                                    &vdev_clone,
                                                    &pressed_clone,
                                                    None,
                                                );
                                                println!("[MacroStat Tamamlandı] '{}' çift dokunma tamamlandı.", macro_name);
                                            });
                                        } else {
                                            tracker.insert(tracker_key, (now, m.double_tap_ms));
                                        }
                                    }
                                    TriggerMode::HOLD_LONG_PRESS => {
                                        let held_c = Arc::clone(&physical_held_keys_arc);
                                        let hold_ms = m.hold_ms;
                                        thread::spawn(move || {
                                            let target = Duration::from_millis(hold_ms);
                                            let start = Instant::now();
                                            while start.elapsed() < target {
                                                if PANIC_STOP.load(Ordering::SeqCst)
                                                    || SHUTDOWN.load(Ordering::SeqCst)
                                                {
                                                    return;
                                                }
                                                let still_held = {
                                                    let held = held_c.read().unwrap();
                                                    held.iter()
                                                        .any(|h| keys_are_equivalent(key, *h))
                                                };
                                                if !still_held {
                                                    return;
                                                }
                                                let remaining =
                                                    target.saturating_sub(start.elapsed());
                                                thread::sleep(
                                                    remaining.min(Duration::from_millis(10)),
                                                );
                                            }
                                            let still_held = {
                                                let held = held_c.read().unwrap();
                                                held.iter().any(|h| keys_are_equivalent(key, *h))
                                            };
                                            if still_held {
                                                println!(
                                                    "[UZUN BASIM] '{}' yürütülüyor (Eşik: {}ms)",
                                                    macro_name, hold_ms
                                                );
                                                execute_macro_actions(
                                                    &actions_clone,
                                                    &vdev_clone,
                                                    &pressed_clone,
                                                    None,
                                                );
                                                println!("[MacroStat Tamamlandı] '{}' uzun basım tamamlandı.", macro_name);
                                            }
                                        });
                                    }
                                    TriggerMode::PRESS_AND_RELEASE => {
                                        if !profile.macros[m.action_index]
                                            .release_actions
                                            .is_empty()
                                        {
                                            press_release_armed.insert(m.id.clone());
                                        }
                                        println!(
                                            "[ÇİFT EYLEM: BASILDI] '{}' yürütülüyor",
                                            macro_name
                                        );
                                        thread::spawn(move || {
                                            execute_macro_actions(
                                                &actions_clone,
                                                &vdev_clone,
                                                &pressed_clone,
                                                None,
                                            );
                                        });
                                    }
                                }
                            }
                        }

                        if is_release {
                            for m in &compiled_macros {
                                if m.mode != TriggerMode::PRESS_AND_RELEASE {
                                    continue;
                                }
                                let trigger_released = if let Some(single) = m.single {
                                    keys_are_equivalent(single, key)
                                } else {
                                    m.combo.iter().any(|k| keys_are_equivalent(*k, key))
                                };
                                if !trigger_released || !press_release_armed.remove(&m.id) {
                                    continue;
                                }
                                let release_actions =
                                    profile.macros[m.action_index].release_actions.clone();
                                if release_actions.is_empty() {
                                    continue;
                                }
                                println!(
                                    "[ÇİFT EYLEM: BIRAKILDI] '{}' bırakış eylemleri yürütülüyor",
                                    m.name
                                );
                                let vdev_c = Arc::clone(&vdev_arc);
                                let pressed_c = Arc::clone(&pressed_keys_arc);
                                thread::spawn(move || {
                                    execute_macro_actions(
                                        &release_actions,
                                        &vdev_c,
                                        &pressed_c,
                                        None,
                                    );
                                });
                            }
                        }
                    }
                }
            }
        } else if ret < 0 {
            let err = std::io::Error::last_os_error();
            if err.raw_os_error() == Some(libc::EINTR) {
                continue;
            }
            thread::sleep(Duration::from_millis(50));
        }
    }

    // Temiz kapanış: basılı kalmış sanal tuş/fare düğmeleri serbest bırakılır.
    PANIC_STOP.store(true, Ordering::SeqCst);
    {
        let toggles = lock(&running_toggles);
        for flag in toggles.values() {
            flag.store(false, Ordering::SeqCst);
        }
    }
    {
        let mut dev = lock(&vdev_arc);
        let mut pressed = lock(&pressed_keys_arc);
        release_all_keys(&mut dev, &mut pressed);
    }
    println!("[MacroStat Motor] Temiz kapanış tamamlandı.");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sanitizes_virtual_device_name() {
        assert_eq!(sanitize_device_name(""), "MacroStat Virtual Engine");
        assert_eq!(sanitize_device_name("   "), "MacroStat Virtual Engine");
        assert_eq!(sanitize_device_name("Klavye\0\x1b"), "Klavye");
        let long = "A".repeat(200);
        assert!(sanitize_device_name(&long).chars().count() <= 80);
        assert!(!sanitize_device_name("Kötü\0Ad").contains('\0'));
    }

    #[test]
    fn parses_common_key_names() {
        assert_eq!(string_to_key("KEY_A"), Some(Key::KEY_A));
        assert_eq!(string_to_key("a"), Some(Key::KEY_A));
        assert_eq!(string_to_key("MOUSE5"), Some(Key::BTN_EXTRA));
        assert_eq!(string_to_key("CODE_30"), Some(Key::new(30)));
        assert_eq!(string_to_key("bilinmeyen-tus"), None);
    }

    #[test]
    fn parse_cli_args_reads_watch_restart() {
        let raw: Vec<String> = [
            "macrostat-daemon",
            "--watch-restart",
            "KEY_F12",
            "profile.json",
        ]
        .iter()
        .map(|value| value.to_string())
        .collect();
        let parsed = parse_cli_args(&raw);
        assert_eq!(parsed.watch_restart_key.as_deref(), Some("KEY_F12"));
        assert_eq!(parsed.config.as_deref(), Some("profile.json"));
    }

    #[test]
    fn left_and_right_modifiers_are_equivalent() {
        assert!(keys_are_equivalent(Key::KEY_LEFTCTRL, Key::KEY_RIGHTCTRL));
        assert!(keys_are_equivalent(Key::KEY_LEFTSHIFT, Key::KEY_RIGHTSHIFT));
        assert!(keys_are_equivalent(Key::KEY_LEFTALT, Key::KEY_RIGHTALT));
        assert!(!keys_are_equivalent(Key::KEY_LEFTCTRL, Key::KEY_LEFTSHIFT));
        assert!(!keys_are_equivalent(Key::KEY_A, Key::KEY_B));
    }

    #[test]
    fn wrapper_profile_selects_active_profile() {
        let json = r#"{"schemaVersion":1,"activeProfileId":"b","profiles":[
            {"id":"a","name":"A","panicKey":"KEY_PAUSE","macros":[]},
            {"id":"b","name":"B","panicKey":"KEY_F9","macros":[
                {"id":"m","name":"M","enabled":true,"triggerKey":"KEY_F8","triggerMode":"ONCE","actions":[]}]}]}"#;
        let p = parse_profile(json).expect("wrapper ayrıştırılmalı");
        assert_eq!(p.id, "b");
        assert_eq!(p.panic_key, "KEY_F9");
        assert_eq!(p.macros.len(), 1);
    }

    #[test]
    fn legacy_single_profile_is_supported() {
        let json = r#"{"id":"legacy","name":"Eski","panicKey":"KEY_PAUSE","macros":[]}"#;
        let p = parse_profile(json).expect("tekil profil ayrıştırılmalı");
        assert_eq!(p.id, "legacy");
    }

    #[test]
    fn malformed_json_is_rejected() {
        assert!(parse_profile("{bozuk").is_none());
        assert!(parse_profile("").is_none());
    }

    #[test]
    fn invalid_trigger_is_skipped() {
        let profile = ProfileConfig {
            id: "p".into(),
            name: "P".into(),
            panic_key: "KEY_PAUSE".into(),
            virtual_device_name: "V".into(),
            macros: vec![
                MacroConfig {
                    id: "bad".into(),
                    name: "Kötü".into(),
                    enabled: true,
                    trigger_key: "KEY_OLMAYAN_TUS".into(),
                    trigger_mode: TriggerMode::ONCE,
                    repeat_count: 1,
                    double_tap_timeout_ms: 300,
                    hold_duration_ms: 300,
                    release_actions: vec![],
                    actions: vec![],
                },
                MacroConfig {
                    id: "ok".into(),
                    name: "İyi".into(),
                    enabled: true,
                    trigger_key: "KEY_F8".into(),
                    trigger_mode: TriggerMode::ONCE,
                    repeat_count: 1,
                    double_tap_timeout_ms: 300,
                    hold_duration_ms: 300,
                    release_actions: vec![],
                    actions: vec![],
                },
            ],
        };
        let compiled = compile_macros(&profile);
        assert_eq!(compiled.len(), 1);
        assert_eq!(compiled[0].trigger_key, "KEY_F8");
    }

    #[test]
    fn mouse_path_action_parses_points() {
        let json = r#"{"type":"MOUSE_PATH","points":[[0,3,-1],[4,5,0],[12,0,2]]}"#;
        let action: MacroAction = serde_json::from_str(json).expect("MOUSE_PATH ayrıştırılmalı");
        assert_eq!(action.r#type, ActionType::MOUSE_PATH);
        let points = action.points.expect("noktalar okunmalı");
        assert_eq!(points.len(), 3);
        assert_eq!(points[1], [4, 5, 0]);
        assert_eq!(action.start, None);
    }

    #[test]
    fn mouse_path_action_parses_start_position() {
        let json = r#"{"type":"MOUSE_PATH","points":[[0,1,2]],"start":[1280,-240]}"#;
        let action: MacroAction = serde_json::from_str(json).expect("başlangıç noktası okunmalı");
        assert_eq!(action.start, Some([1280, -240]));
    }

    #[test]
    fn mouse_path_requires_valid_point_shape() {
        let json = r#"{"type":"MOUSE_PATH","points":[[0,1,2],[4,5]]}"#;
        assert!(serde_json::from_str::<MacroAction>(json).is_err());
    }

    #[test]
    fn canonical_ids_group_modifier_sides() {
        assert_eq!(
            canonical_key_id(Key::KEY_LEFTCTRL),
            canonical_key_id(Key::KEY_RIGHTCTRL)
        );
        assert_ne!(canonical_key_id(Key::KEY_A), canonical_key_id(Key::KEY_B));
    }

    #[test]
    fn combo_matches_only_while_all_keys_held() {
        let profile = ProfileConfig {
            id: "p".into(),
            name: "P".into(),
            panic_key: "KEY_PAUSE".into(),
            virtual_device_name: "V".into(),
            macros: vec![MacroConfig {
                id: "m".into(),
                name: "M".into(),
                enabled: true,
                trigger_key: "KEY_LEFTSHIFT+KEY_LEFTCTRL".into(),
                trigger_mode: TriggerMode::ONCE,
                repeat_count: 1,
                double_tap_timeout_ms: 300,
                hold_duration_ms: 300,
                release_actions: vec![],
                actions: vec![],
            }],
        };
        let compiled = compile_macros(&profile);
        assert_eq!(compiled.len(), 1);

        let mut held = HashSet::new();
        held.insert(Key::KEY_LEFTCTRL);
        assert!(!trigger_matches(
            &compiled[0],
            Key::KEY_LEFTCTRL,
            true,
            &held
        ));

        held.insert(Key::KEY_RIGHTSHIFT);
        assert!(trigger_matches(
            &compiled[0],
            Key::KEY_RIGHTSHIFT,
            true,
            &held
        ));
        assert!(!trigger_matches(
            &compiled[0],
            Key::KEY_LEFTSHIFT,
            false,
            &held
        ));
    }

    #[test]
    fn profile_reader_rejects_symlinks() {
        let dir = std::env::temp_dir().join(format!(
            "macrostat-profile-link-{}-{:?}",
            std::process::id(),
            std::thread::current().id()
        ));
        fs::create_dir_all(&dir).expect("geçici dizin");
        let target = dir.join("real.json");
        fs::write(&target, "{}").expect("hedef profil");
        let link = dir.join("link.json");
        std::os::unix::fs::symlink(&target, &link).expect("sembolik bağ");
        let err = read_profile_text(&link, 1024).expect_err("sembolik bağ reddedilmeli");
        assert_eq!(err.raw_os_error(), Some(libc::ELOOP));
        let _ = fs::remove_file(&link);
        let _ = fs::remove_file(&target);
        let _ = fs::remove_dir(&dir);
    }

    #[test]
    fn profile_reader_enforces_size_limit() {
        let path = std::env::temp_dir().join(format!(
            "macrostat-profile-size-{}-{:?}.json",
            std::process::id(),
            std::thread::current().id()
        ));
        fs::write(&path, "x".repeat(200)).expect("geçici profil dosyası");
        assert!(read_profile_text(&path, 200).is_ok());
        let err = read_profile_text(&path, 199).expect_err("sınır aşılmalı");
        assert_eq!(err.kind(), std::io::ErrorKind::InvalidData);
        let _ = fs::remove_file(&path);
    }

    #[test]
    fn lock_file_ownership_is_verified() {
        let path = std::env::temp_dir().join(format!(
            "macrostat-lock-ownership-{}-{:?}.lock",
            std::process::id(),
            std::thread::current().id()
        ));
        let file = fs::OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(&path)
            .expect("geçici kilit dosyası");
        let uid = unsafe { libc::getuid() };
        assert!(lock_file_owned_by(&file, uid));
        assert!(!lock_file_owned_by(&file, uid.wrapping_add(1)));
        drop(file);
        let _ = fs::remove_file(&path);
    }
}
