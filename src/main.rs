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

static PANIC_STOP: AtomicBool = AtomicBool::new(false);
static SHUTDOWN: AtomicBool = AtomicBool::new(false);
/// GUI kaydettiğinde motoru yeniden başlatmadan profili tazelemek için.
static RELOAD: AtomicBool = AtomicBool::new(false);
/// Aynı anda birden fazla makro thread'inin sanal tuş durumunu birbirine
/// karıştırmasını önlemek için tek yürütme kilidi.
static ACTION_LOCK: Mutex<()> = Mutex::new(());

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
    if warned.lock().unwrap().insert(c) {
        eprintln!(
            "[UYARI] '{}' karakteri TEXT eyleminde desteklenmiyor (yalnızca US-ASCII); atlandı.",
            c
        );
    }
}

fn create_virtual_device(name: &str) -> VirtualDevice {
    let dev_name = if name.is_empty() {
        "MacroStat Virtual Engine"
    } else {
        name
    };
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
            if let Ok(b2) = builder.name(dev_name).with_keys(&keys) {
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
        .name(dev_name)
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
            let mut dev = vdev.lock().unwrap();
            let mut pressed = pressed_keys.lock().unwrap();
            release_all_keys(&mut dev, &mut pressed);
            return false;
        }

        let mut dev = vdev.lock().unwrap();
        let mut pressed = pressed_keys.lock().unwrap();

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
                            let mut d = vdev.lock().unwrap();
                            let mut p = pressed_keys.lock().unwrap();
                            release_all_keys(&mut d, &mut p);
                            return false;
                        }
                        let mut dev2 = vdev.lock().unwrap();
                        let mut pressed2 = pressed_keys.lock().unwrap();
                        emit_key(&mut dev2, key, 0);
                        pressed2.remove(&key);
                        drop(dev2);
                        drop(pressed2);
                        if !cancellable_sleep(10, 0, stop_flag) {
                            let mut d = vdev.lock().unwrap();
                            let mut p = pressed_keys.lock().unwrap();
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
                            let mut d = vdev.lock().unwrap();
                            let mut p = pressed_keys.lock().unwrap();
                            release_all_keys(&mut d, &mut p);
                            return false;
                        }
                        let mut dev2 = vdev.lock().unwrap();
                        let mut pressed2 = pressed_keys.lock().unwrap();
                        emit_key(&mut dev2, btn, 0);
                        pressed2.remove(&btn);
                        drop(dev2);
                        drop(pressed2);
                        if !cancellable_sleep(10, 0, stop_flag) {
                            let mut d = vdev.lock().unwrap();
                            let mut p = pressed_keys.lock().unwrap();
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
                            let mut d = vdev.lock().unwrap();
                            let mut p = pressed_keys.lock().unwrap();
                            release_all_keys(&mut d, &mut p);
                            return false;
                        }
                        if let Some((key, with_shift)) = char_to_evdev_key(ch) {
                            let mut dev_c = vdev.lock().unwrap();
                            if with_shift {
                                emit_key(&mut dev_c, Key::KEY_LEFTSHIFT, 1);
                                // İzlenen sete eklenmezse iptal/STOP anında Shift takılı kalır.
                                pressed_keys.lock().unwrap().insert(Key::KEY_LEFTSHIFT);
                                drop(dev_c);
                                if !cancellable_sleep(8, 0, stop_flag) {
                                    let mut d = vdev.lock().unwrap();
                                    let mut p = pressed_keys.lock().unwrap();
                                    release_all_keys(&mut d, &mut p);
                                    return false;
                                }
                                dev_c = vdev.lock().unwrap();
                            }
                            emit_key(&mut dev_c, key, 1);
                            drop(dev_c);
                            if !cancellable_sleep(16, 0, stop_flag) {
                                let mut d = vdev.lock().unwrap();
                                let mut p = pressed_keys.lock().unwrap();
                                release_all_keys(&mut d, &mut p);
                                return false;
                            }
                            let mut dev_c2 = vdev.lock().unwrap();
                            emit_key(&mut dev_c2, key, 0);
                            if with_shift {
                                drop(dev_c2);
                                if !cancellable_sleep(8, 0, stop_flag) {
                                    let mut d = vdev.lock().unwrap();
                                    let mut p = pressed_keys.lock().unwrap();
                                    release_all_keys(&mut d, &mut p);
                                    return false;
                                }
                                dev_c2 = vdev.lock().unwrap();
                                emit_key(&mut dev_c2, Key::KEY_LEFTSHIFT, 0);
                                pressed_keys.lock().unwrap().remove(&Key::KEY_LEFTSHIFT);
                            }
                            drop(dev_c2);
                            if !cancellable_sleep(16, 0, stop_flag) {
                                let mut d = vdev.lock().unwrap();
                                let mut p = pressed_keys.lock().unwrap();
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
                    let mut d = vdev.lock().unwrap();
                    let mut p = pressed_keys.lock().unwrap();
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
const DEFAULT_PROFILE_JSON: &str = include_str!("../profile.json");

extern "C" fn handle_termination(_signal: libc::c_int) {
    // Sinyal işleyicisi yalnızca atomik bayrak yazar; temizlik ana döngüde yapılır.
    SHUTDOWN.store(true, Ordering::SeqCst);
}

extern "C" fn handle_reload(_signal: libc::c_int) {
    RELOAD.store(true, Ordering::SeqCst);
}

/// Aynı kullanıcı için ikinci bir motorun başlamasını engeller.
/// Kilit süreç yaşadığı sürece tutulur; süreç ölünce kernel kilidi bırakır.
fn acquire_single_instance_lock() -> Option<fs::File> {
    let uid = unsafe { libc::getuid() };
    let candidates = [
        format!("/run/user/{}/cachymacro.lock", uid),
        format!("/tmp/cachymacro-{}.lock", uid),
    ];
    for path in candidates {
        match fs::OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(&path)
        {
            Ok(file) => {
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

fn load_profile_file(config_path: &Path) -> ProfileConfig {
    if config_path.exists() {
        println!(
            "[BİLGİ] Yapılandırma dosyası okunuyor: {}",
            config_path.display()
        );
        match fs::read_to_string(config_path) {
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
        let mut dev = vdev.lock().unwrap();
        let mut keys = pressed.lock().unwrap();
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

    // Argümanlar: [--test-macro <id>] [profil.json]
    let raw_args: Vec<String> = std::env::args().collect();
    let mut test_macro_id: Option<String> = None;
    let mut config_arg: Option<String> = None;
    let mut args_iter = raw_args.iter().skip(1);
    while let Some(arg) = args_iter.next() {
        if arg == "--test-macro" {
            test_macro_id = args_iter.next().cloned();
        } else if !arg.starts_with("--") {
            config_arg = Some(arg.clone());
        }
    }
    let config_path = config_arg
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
    if let Some(macro_id) = &test_macro_id {
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

    loop {
        if SHUTDOWN.load(Ordering::SeqCst) {
            println!("[MacroStat Motor] Kapanış sinyali alındı. Motor kapatılıyor.");
            break;
        }
        if unsafe { libc::getppid() } == 1 {
            println!("[MacroStat Motor] Ana uygulama sonlandırıldı. Motor kapatılıyor.");
            break;
        }

        // 3. GUI'den SIGUSR1 geldiyse profili yeniden başlatmadan tazele.
        if RELOAD.swap(false, Ordering::SeqCst) {
            match fs::read_to_string(&config_path)
                .ok()
                .and_then(|c| parse_profile(&c))
            {
                Some(new_profile) => {
                    {
                        let toggles = running_toggles.lock().unwrap();
                        for flag in toggles.values() {
                            flag.store(false, Ordering::SeqCst);
                        }
                    }
                    running_toggles.lock().unwrap().clear();
                    {
                        let mut dev = vdev_arc.lock().unwrap();
                        let mut pressed = pressed_keys_arc.lock().unwrap();
                        release_all_keys(&mut dev, &mut pressed);
                    }
                    latched_combos.clear();
                    press_release_armed.clear();
                    double_tap_tracker.lock().unwrap().clear();

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
                                let mut toggles = running_toggles.lock().unwrap();
                                for flag in toggles.values() {
                                    flag.store(false, Ordering::SeqCst);
                                }
                                toggles.clear();
                            }
                            {
                                let mut dev = vdev_arc.lock().unwrap();
                                let mut pressed = pressed_keys_arc.lock().unwrap();
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
                                        let mut toggles = running_toggles.lock().unwrap();
                                        if let Some(flag) = toggles.get(&macro_id_key) {
                                            if flag.load(Ordering::SeqCst) {
                                                println!("[DÖNGÜ KAPATILDI] Tetikleyiciye tekrar basıldı, makro durduruldu: '{}'", macro_name);
                                                flag.store(false, Ordering::SeqCst);
                                                toggles.remove(&macro_id_key);
                                                drop(toggles);
                                                let mut dev = vdev_arc.lock().unwrap();
                                                let mut pressed = pressed_keys_arc.lock().unwrap();
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
                                                let mut dev = vdev_c.lock().unwrap();
                                                let mut pressed = pressed_c.lock().unwrap();
                                                release_all_keys(&mut dev, &mut pressed);
                                            }
                                            {
                                                let mut t = toggles_ref.lock().unwrap();
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
                                                let mut dev = vdev_c.lock().unwrap();
                                                let mut pressed = pressed_c.lock().unwrap();
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
                                        let mut tracker = double_tap_tracker.lock().unwrap();
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
        let toggles = running_toggles.lock().unwrap();
        for flag in toggles.values() {
            flag.store(false, Ordering::SeqCst);
        }
    }
    {
        let mut dev = vdev_arc.lock().unwrap();
        let mut pressed = pressed_keys_arc.lock().unwrap();
        release_all_keys(&mut dev, &mut pressed);
    }
    println!("[MacroStat Motor] Temiz kapanış tamamlandı.");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_common_key_names() {
        assert_eq!(string_to_key("KEY_A"), Some(Key::KEY_A));
        assert_eq!(string_to_key("a"), Some(Key::KEY_A));
        assert_eq!(string_to_key("MOUSE5"), Some(Key::BTN_EXTRA));
        assert_eq!(string_to_key("CODE_30"), Some(Key::new(30)));
        assert_eq!(string_to_key("bilinmeyen-tus"), None);
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
}
