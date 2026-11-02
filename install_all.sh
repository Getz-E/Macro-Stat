#!/bin/bash
# ==============================================================================
# MacroStat - CachyOS / Arch Linux Otomatik Kurulum ve Çalıştırma Betiği
# ==============================================================================
set -e

echo "🚀 [1/6] Sistem paketleri kontrol ediliyor..."
if command -v pacman &> /dev/null; then
    sudo pacman -S --needed --noconfirm rust cargo libevdev pkgconf python python-pyqt6 || true
fi

echo "📁 [2/6] Proje dosyaları hazırlanıyor..."
mkdir -p cachymacro/src

cat << 'EOF' > cachymacro/Cargo.toml
[package]
name = "cachymacro-daemon"
version = "1.0.0"
edition = "2021"
authors = ["MacroStat Author"]
description = "Ultra Low Latency Linux Macro Engine for CachyOS and KDE Plasma"

[dependencies]
evdev = { version = "0.12", features = ["tokio"] }
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
rand = "0.8"
libc = "0.2"

[profile.release]
opt-level = 3
lto = true
codegen-units = 1
panic = "abort"
strip = true

EOF

cat << 'EOF' > cachymacro/src/main.rs
// MacroStat Rust Daemon - Linux evdev / uinput Zero Latency Engine
#![allow(non_camel_case_types)]

use std::collections::{HashMap, HashSet};
use std::fs;
use std::os::unix::io::AsRawFd;
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, RwLock};
use std::thread;
use std::time::{Duration, Instant};

use evdev::uinput::{VirtualDevice, VirtualDeviceBuilder};
use evdev::{AttributeSet, EventType, InputEvent, Key, RelativeAxisType};
use rand::Rng;
use serde::{Deserialize, Serialize};

static PANIC_STOP: AtomicBool = AtomicBool::new(false);

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ActionType {
    #[serde(alias = "key_down", alias = "KEY_DOWN", alias = "KeyDown", alias = "keyDown")]
    KEY_DOWN,
    #[serde(alias = "key_up", alias = "KEY_UP", alias = "KeyUp", alias = "keyUp")]
    KEY_UP,
    #[serde(alias = "key_tap", alias = "KEY_TAP", alias = "KeyTap", alias = "keyTap")]
    KEY_TAP,
    #[serde(alias = "mouse_down", alias = "MOUSE_DOWN", alias = "MouseDown", alias = "mouseDown")]
    MOUSE_DOWN,
    #[serde(alias = "mouse_up", alias = "MOUSE_UP", alias = "MouseUp", alias = "mouseUp")]
    MOUSE_UP,
    #[serde(alias = "mouse_click", alias = "MOUSE_CLICK", alias = "MouseClick", alias = "mouseClick")]
    MOUSE_CLICK,
    #[serde(alias = "mouse_move", alias = "MOUSE_MOVE", alias = "MouseMove", alias = "mouseMove")]
    MOUSE_MOVE,
    #[serde(alias = "mouse_scroll", alias = "MOUSE_SCROLL", alias = "MouseScroll", alias = "mouseScroll")]
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
    #[serde(alias = "while_held", alias = "WHILE_HELD", alias = "WhileHeld", alias = "whileHeld")]
    WHILE_HELD,
    #[serde(alias = "toggle_loop", alias = "TOGGLE_LOOP", alias = "ToggleLoop", alias = "toggleLoop")]
    TOGGLE_LOOP,
    #[serde(alias = "repeat_count", alias = "REPEAT_COUNT", alias = "RepeatCount", alias = "repeatCount")]
    REPEAT_COUNT,
    #[serde(alias = "double_tap", alias = "DOUBLE_TAP", alias = "DoubleTap", alias = "doubleTap")]
    DOUBLE_TAP,
    #[serde(alias = "hold_long_press", alias = "HOLD_LONG_PRESS", alias = "HoldLongPress", alias = "holdLongPress", alias = "hold")]
    HOLD_LONG_PRESS,
    #[serde(alias = "press_and_release", alias = "PRESS_AND_RELEASE", alias = "PressAndRelease", alias = "pressAndRelease")]
    PRESS_AND_RELEASE,
}

fn default_macro_name() -> String { "Yeni Makro".to_string() }
fn default_true() -> bool { true }
fn default_trigger_mode() -> TriggerMode { TriggerMode::ONCE }
fn default_repeat_count() -> u32 { 1 }
fn default_double_tap_timeout() -> u64 { 300 }
fn default_hold_duration() -> u64 { 300 }

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
    #[serde(rename = "triggerMode", alias = "trigger_mode", default = "default_trigger_mode")]
    pub trigger_mode: TriggerMode,
    #[serde(rename = "repeatCount", alias = "repeat_count", default = "default_repeat_count")]
    pub repeat_count: u32,
    #[serde(rename = "doubleTapTimeoutMs", alias = "double_tap_timeout_ms", default = "default_double_tap_timeout")]
    pub double_tap_timeout_ms: u64,
    #[serde(rename = "holdDurationMs", alias = "hold_duration_ms", default = "default_hold_duration")]
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
        "BTN_MIDDLE" | "MIDDLE" | "MOUSE_3" | "MOUSE3" | "M3" | "MIDDLECLICK" => Some(Key::BTN_MIDDLE),
        "BTN_SIDE" | "SIDE" | "MOUSE_4" | "MOUSE4" | "M4" | "M4_SIDE" | "BTN_BACK" | "BACK" => Some(Key::BTN_SIDE),
        "BTN_EXTRA" | "EXTRA" | "MOUSE_5" | "MOUSE5" | "M5" | "M5_SIDE" | "BTN_FORWARD" | "FORWARD" => Some(Key::BTN_EXTRA),

        _ => None,
    }
}

fn keys_are_equivalent(k1: Key, k2: Key) -> bool {
    if k1 == k2 { return true; }
    let is_ctrl = (k1 == Key::KEY_LEFTCTRL || k1 == Key::KEY_RIGHTCTRL) && (k2 == Key::KEY_LEFTCTRL || k2 == Key::KEY_RIGHTCTRL);
    let is_shift = (k1 == Key::KEY_LEFTSHIFT || k1 == Key::KEY_RIGHTSHIFT) && (k2 == Key::KEY_LEFTSHIFT || k2 == Key::KEY_RIGHTSHIFT);
    let is_alt = (k1 == Key::KEY_LEFTALT || k1 == Key::KEY_RIGHTALT) && (k2 == Key::KEY_LEFTALT || k2 == Key::KEY_RIGHTALT);
    let is_meta = (k1 == Key::KEY_LEFTMETA || k1 == Key::KEY_RIGHTMETA) && (k2 == Key::KEY_LEFTMETA || k2 == Key::KEY_RIGHTMETA);
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

fn create_virtual_device(name: &str) -> VirtualDevice {
    let dev_name = if name.is_empty() { "MacroStat Virtual Engine" } else { name };
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
    if ms == 0 { return true; }
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
        if PANIC_STOP.load(Ordering::SeqCst) || stop_flag.map_or(false, |f| !f.load(Ordering::SeqCst)) {
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
    for action in actions {
        if PANIC_STOP.load(Ordering::SeqCst) || stop_flag.map_or(false, |f| !f.load(Ordering::SeqCst)) {
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
                        if PANIC_STOP.load(Ordering::SeqCst) || stop_flag.map_or(false, |f| !f.load(Ordering::SeqCst)) {
                            let mut d = vdev.lock().unwrap();
                            let mut p = pressed_keys.lock().unwrap();
                            release_all_keys(&mut d, &mut p);
                            return false;
                        }
                        if let Some((key, with_shift)) = char_to_evdev_key(ch) {
                            let mut dev_c = vdev.lock().unwrap();
                            if with_shift {
                                emit_key(&mut dev_c, Key::KEY_LEFTSHIFT, 1);
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
                            }
                            drop(dev_c2);
                            if !cancellable_sleep(16, 0, stop_flag) {
                                let mut d = vdev.lock().unwrap();
                                let mut p = pressed_keys.lock().unwrap();
                                release_all_keys(&mut d, &mut p);
                                return false;
                            }
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

fn discover_devices() -> (Vec<evdev::Device>, usize) {
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
                                if name.contains("MacroStat") || name.contains("CachyMacro") || name.contains("Virtual Engine") {
                                    continue;
                                }
                            }
                            let is_input = if let Some(keys) = dev.supported_keys() {
                                keys.iter().count() > 0
                            } else {
                                false
                            };

                            if is_input {
                                println!(" -> [Aygıt Bağlandı] {} ({})", dev.name().unwrap_or("Giriş Aygıtı"), path.display());
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

fn main() {
    // Linux PR_SET_PDEATHSIG: Ana GUI kapandığında kernel bu motoru derhal SIGTERM ile sonlandırır
    unsafe {
        libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGTERM);
    }

    println!("=======================================================");
    println!("  MacroStat Daemon - Linux (CachyOS/KDE) Makro Motoru ");
    println!("  Wayland & X11 | Panic Switch: KEY_PAUSE ");
    println!("=======================================================");

    let args: Vec<String> = std::env::args().collect();
    let config_path = if args.len() > 1 && Path::new(&args[1]).exists() {
        Path::new(&args[1]).to_path_buf()
    } else if Path::new("profile.json").exists() {
        Path::new("profile.json").to_path_buf()
    } else {
        Path::new("profile.json").to_path_buf()
    };

    let profile: ProfileConfig = if config_path.exists() {
        println!("[BİLGİ] Yapılandırma dosyası okunuyor: {}", config_path.display());
        match fs::read_to_string(&config_path) {
            Ok(contents) => {
                if let Ok(wrapper) = serde_json::from_str::<MultiProfileWrapper>(&contents) {
                    if !wrapper.profiles.is_empty() {
                        let active_id = wrapper.active_profile_id.unwrap_or_default();
                        let selected = wrapper.profiles.iter().find(|p| p.id == active_id).cloned().unwrap_or_else(|| wrapper.profiles[0].clone());
                        println!("[BAŞARILI] Çoklu Profil Yapılandırması Yüklendi! (Toplam {} profil mevcut)", wrapper.profiles.len());
                        println!("[İZOLASYON AKTİF] Seçili Aktif Profil: '{}' ({} makro). Diğer profiller devre dışıdır.", selected.name, selected.macros.len());
                        selected
                    } else {
                        serde_json::from_str::<ProfileConfig>(&contents).unwrap_or_else(|_| serde_json::from_str::<ProfileConfig>(r#"{"id":"profile-cachy-default","name":"MacroStat Varsayılan Profil","description":"CachyOS & KDE Plasma için donanım tabanlı sıfır gecikmeli makrolar","panicKey":"KEY_PAUSE","virtualDeviceName":"MacroStat Virtual Engine","defaultJitterMs":2,"macros":[{"id":"macro-turbo-shift-ctrl","name":"Shift+Ctrl Çift Tuş Tetikleyici","description":"LeftShift + LeftCtrl kombinasyonuna basıldığında hızlı X tuşu tetikler.","enabled":true,"triggerKey":"KEY_LEFTSHIFT+KEY_LEFTCTRL","triggerMode":"ONCE","repeatCount":1,"tags":["Kombinasyon","Oyun"],"actions":[{"id":"a1","type":"KEY_DOWN","key":"KEY_X","description":"X tuşuna basılı tut"},{"id":"a2","type":"DELAY","delayMs":40,"jitterMs":2,"description":"40ms bekle"},{"id":"a3","type":"KEY_UP","key":"KEY_X","description":"X tuşunu bırak"}],"createdAt":1793259933773,"updatedAt":1793259933773},{"id":"macro-burst-clicker","name":"Mouse 5 Hızlı Tıklama","description":"Fare yan tuşuna (M5) basıldığında sol tık bas-çek yapar.","enabled":true,"triggerKey":"BTN_EXTRA","triggerMode":"ONCE","repeatCount":1,"tags":["Fare","FPS"],"actions":[{"id":"m1","type":"MOUSE_DOWN","mouseButton":"LEFT","description":"Sol fare tuşuna bas"},{"id":"m2","type":"DELAY","delayMs":25,"jitterMs":2,"description":"25ms bekle"},{"id":"m3","type":"MOUSE_UP","mouseButton":"LEFT","description":"Sol fareyi bırak"}],"createdAt":1793256333773,"updatedAt":1793256333773},{"id":"macro-fast-macro","name":"F8 Seri Metin & Enter","description":"F8 tuşuyla hızlı terminal komutunu enjekte eder.","enabled":true,"triggerKey":"KEY_F8","triggerMode":"ONCE","repeatCount":1,"tags":["Otomasyon","Terminal"],"actions":[{"id":"t1","type":"TEXT","text":"uname -r","description":"Metin yazdır"},{"id":"t2","type":"DELAY","delayMs":30,"jitterMs":1,"description":"30ms bekle"},{"id":"t3","type":"KEY_TAP","key":"KEY_ENTER","description":"Enter tuşuna bas"}],"createdAt":1793252733773,"updatedAt":1793252733773},{"id":"macro-yr3d5pt","name":"Yeni Makro","description":"Kullanıcı tanımlı makro","enabled":true,"triggerKey":"KEY_A","triggerMode":"ONCE","repeatCount":1,"actions":[{"id":"act-1","type":"KEY_TAP","key":"KEY_X","delayMs":20},{"id":"act-2","type":"DELAY","delayMs":40,"jitterMs":2},{"id":"act-fe26ncx","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-8i710su","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-93gxpmh","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-ar49xhc","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-6hou3hh","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-arhp3t0","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-dvatjb8","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-y60omil","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-qircjy0","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-tdvknfk","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-up7xewj","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-xrzdr6n","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-rn63mnz","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-8kjt2c4","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-5r2yzwp","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-e8ajn17","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-u6srr2t","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-37r7neq","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-1mka5fl","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-j6j9ypu","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-6fk2ujv","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-q7w6e3j","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-71ltn10","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"}],"tags":["Özel"],"createdAt":1793269706930,"updatedAt":1793269706930}]}"#).unwrap())
                    }
                } else if let Ok(p) = serde_json::from_str::<ProfileConfig>(&contents) {
                    println!("[BAŞARILI] Profil başarıyla yüklendi: {} ({} makro)", p.name, p.macros.len());
                    p
                } else {
                    eprintln!("[UYARI] profile.json ayrıştırılamadı. Varsayılan profil kullanılıyor.");
                    serde_json::from_str::<ProfileConfig>(r#"{"id":"profile-cachy-default","name":"MacroStat Varsayılan Profil","description":"CachyOS & KDE Plasma için donanım tabanlı sıfır gecikmeli makrolar","panicKey":"KEY_PAUSE","virtualDeviceName":"MacroStat Virtual Engine","defaultJitterMs":2,"macros":[{"id":"macro-turbo-shift-ctrl","name":"Shift+Ctrl Çift Tuş Tetikleyici","description":"LeftShift + LeftCtrl kombinasyonuna basıldığında hızlı X tuşu tetikler.","enabled":true,"triggerKey":"KEY_LEFTSHIFT+KEY_LEFTCTRL","triggerMode":"ONCE","repeatCount":1,"tags":["Kombinasyon","Oyun"],"actions":[{"id":"a1","type":"KEY_DOWN","key":"KEY_X","description":"X tuşuna basılı tut"},{"id":"a2","type":"DELAY","delayMs":40,"jitterMs":2,"description":"40ms bekle"},{"id":"a3","type":"KEY_UP","key":"KEY_X","description":"X tuşunu bırak"}],"createdAt":1793259933773,"updatedAt":1793259933773},{"id":"macro-burst-clicker","name":"Mouse 5 Hızlı Tıklama","description":"Fare yan tuşuna (M5) basıldığında sol tık bas-çek yapar.","enabled":true,"triggerKey":"BTN_EXTRA","triggerMode":"ONCE","repeatCount":1,"tags":["Fare","FPS"],"actions":[{"id":"m1","type":"MOUSE_DOWN","mouseButton":"LEFT","description":"Sol fare tuşuna bas"},{"id":"m2","type":"DELAY","delayMs":25,"jitterMs":2,"description":"25ms bekle"},{"id":"m3","type":"MOUSE_UP","mouseButton":"LEFT","description":"Sol fareyi bırak"}],"createdAt":1793256333773,"updatedAt":1793256333773},{"id":"macro-fast-macro","name":"F8 Seri Metin & Enter","description":"F8 tuşuyla hızlı terminal komutunu enjekte eder.","enabled":true,"triggerKey":"KEY_F8","triggerMode":"ONCE","repeatCount":1,"tags":["Otomasyon","Terminal"],"actions":[{"id":"t1","type":"TEXT","text":"uname -r","description":"Metin yazdır"},{"id":"t2","type":"DELAY","delayMs":30,"jitterMs":1,"description":"30ms bekle"},{"id":"t3","type":"KEY_TAP","key":"KEY_ENTER","description":"Enter tuşuna bas"}],"createdAt":1793252733773,"updatedAt":1793252733773},{"id":"macro-yr3d5pt","name":"Yeni Makro","description":"Kullanıcı tanımlı makro","enabled":true,"triggerKey":"KEY_A","triggerMode":"ONCE","repeatCount":1,"actions":[{"id":"act-1","type":"KEY_TAP","key":"KEY_X","delayMs":20},{"id":"act-2","type":"DELAY","delayMs":40,"jitterMs":2},{"id":"act-fe26ncx","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-8i710su","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-93gxpmh","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-ar49xhc","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-6hou3hh","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-arhp3t0","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-dvatjb8","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-y60omil","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-qircjy0","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-tdvknfk","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-up7xewj","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-xrzdr6n","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-rn63mnz","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-8kjt2c4","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-5r2yzwp","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-e8ajn17","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-u6srr2t","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-37r7neq","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-1mka5fl","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-j6j9ypu","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-6fk2ujv","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-q7w6e3j","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-71ltn10","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"}],"tags":["Özel"],"createdAt":1793269706930,"updatedAt":1793269706930}]}"#).unwrap()
                }
            }
            Err(e) => {
                eprintln!("[UYARI] profile.json okunamadı: {}. Varsayılan profil kullanılıyor.", e);
                serde_json::from_str::<ProfileConfig>(r#"{"id":"profile-cachy-default","name":"MacroStat Varsayılan Profil","description":"CachyOS & KDE Plasma için donanım tabanlı sıfır gecikmeli makrolar","panicKey":"KEY_PAUSE","virtualDeviceName":"MacroStat Virtual Engine","defaultJitterMs":2,"macros":[{"id":"macro-turbo-shift-ctrl","name":"Shift+Ctrl Çift Tuş Tetikleyici","description":"LeftShift + LeftCtrl kombinasyonuna basıldığında hızlı X tuşu tetikler.","enabled":true,"triggerKey":"KEY_LEFTSHIFT+KEY_LEFTCTRL","triggerMode":"ONCE","repeatCount":1,"tags":["Kombinasyon","Oyun"],"actions":[{"id":"a1","type":"KEY_DOWN","key":"KEY_X","description":"X tuşuna basılı tut"},{"id":"a2","type":"DELAY","delayMs":40,"jitterMs":2,"description":"40ms bekle"},{"id":"a3","type":"KEY_UP","key":"KEY_X","description":"X tuşunu bırak"}],"createdAt":1793259933773,"updatedAt":1793259933773},{"id":"macro-burst-clicker","name":"Mouse 5 Hızlı Tıklama","description":"Fare yan tuşuna (M5) basıldığında sol tık bas-çek yapar.","enabled":true,"triggerKey":"BTN_EXTRA","triggerMode":"ONCE","repeatCount":1,"tags":["Fare","FPS"],"actions":[{"id":"m1","type":"MOUSE_DOWN","mouseButton":"LEFT","description":"Sol fare tuşuna bas"},{"id":"m2","type":"DELAY","delayMs":25,"jitterMs":2,"description":"25ms bekle"},{"id":"m3","type":"MOUSE_UP","mouseButton":"LEFT","description":"Sol fareyi bırak"}],"createdAt":1793256333773,"updatedAt":1793256333773},{"id":"macro-fast-macro","name":"F8 Seri Metin & Enter","description":"F8 tuşuyla hızlı terminal komutunu enjekte eder.","enabled":true,"triggerKey":"KEY_F8","triggerMode":"ONCE","repeatCount":1,"tags":["Otomasyon","Terminal"],"actions":[{"id":"t1","type":"TEXT","text":"uname -r","description":"Metin yazdır"},{"id":"t2","type":"DELAY","delayMs":30,"jitterMs":1,"description":"30ms bekle"},{"id":"t3","type":"KEY_TAP","key":"KEY_ENTER","description":"Enter tuşuna bas"}],"createdAt":1793252733773,"updatedAt":1793252733773},{"id":"macro-yr3d5pt","name":"Yeni Makro","description":"Kullanıcı tanımlı makro","enabled":true,"triggerKey":"KEY_A","triggerMode":"ONCE","repeatCount":1,"actions":[{"id":"act-1","type":"KEY_TAP","key":"KEY_X","delayMs":20},{"id":"act-2","type":"DELAY","delayMs":40,"jitterMs":2},{"id":"act-fe26ncx","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-8i710su","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-93gxpmh","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-ar49xhc","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-6hou3hh","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-arhp3t0","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-dvatjb8","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-y60omil","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-qircjy0","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-tdvknfk","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-up7xewj","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-xrzdr6n","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-rn63mnz","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-8kjt2c4","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-5r2yzwp","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-e8ajn17","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-u6srr2t","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-37r7neq","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-1mka5fl","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-j6j9ypu","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-6fk2ujv","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-q7w6e3j","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-71ltn10","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"}],"tags":["Özel"],"createdAt":1793269706930,"updatedAt":1793269706930}]}"#).unwrap()
            }
        }
    } else {
        println!("[BİLGİ] profile.json bulunamadı, varsayılan profil yükleniyor.");
        serde_json::from_str::<ProfileConfig>(r#"{"id":"profile-cachy-default","name":"MacroStat Varsayılan Profil","description":"CachyOS & KDE Plasma için donanım tabanlı sıfır gecikmeli makrolar","panicKey":"KEY_PAUSE","virtualDeviceName":"MacroStat Virtual Engine","defaultJitterMs":2,"macros":[{"id":"macro-turbo-shift-ctrl","name":"Shift+Ctrl Çift Tuş Tetikleyici","description":"LeftShift + LeftCtrl kombinasyonuna basıldığında hızlı X tuşu tetikler.","enabled":true,"triggerKey":"KEY_LEFTSHIFT+KEY_LEFTCTRL","triggerMode":"ONCE","repeatCount":1,"tags":["Kombinasyon","Oyun"],"actions":[{"id":"a1","type":"KEY_DOWN","key":"KEY_X","description":"X tuşuna basılı tut"},{"id":"a2","type":"DELAY","delayMs":40,"jitterMs":2,"description":"40ms bekle"},{"id":"a3","type":"KEY_UP","key":"KEY_X","description":"X tuşunu bırak"}],"createdAt":1793259933773,"updatedAt":1793259933773},{"id":"macro-burst-clicker","name":"Mouse 5 Hızlı Tıklama","description":"Fare yan tuşuna (M5) basıldığında sol tık bas-çek yapar.","enabled":true,"triggerKey":"BTN_EXTRA","triggerMode":"ONCE","repeatCount":1,"tags":["Fare","FPS"],"actions":[{"id":"m1","type":"MOUSE_DOWN","mouseButton":"LEFT","description":"Sol fare tuşuna bas"},{"id":"m2","type":"DELAY","delayMs":25,"jitterMs":2,"description":"25ms bekle"},{"id":"m3","type":"MOUSE_UP","mouseButton":"LEFT","description":"Sol fareyi bırak"}],"createdAt":1793256333773,"updatedAt":1793256333773},{"id":"macro-fast-macro","name":"F8 Seri Metin & Enter","description":"F8 tuşuyla hızlı terminal komutunu enjekte eder.","enabled":true,"triggerKey":"KEY_F8","triggerMode":"ONCE","repeatCount":1,"tags":["Otomasyon","Terminal"],"actions":[{"id":"t1","type":"TEXT","text":"uname -r","description":"Metin yazdır"},{"id":"t2","type":"DELAY","delayMs":30,"jitterMs":1,"description":"30ms bekle"},{"id":"t3","type":"KEY_TAP","key":"KEY_ENTER","description":"Enter tuşuna bas"}],"createdAt":1793252733773,"updatedAt":1793252733773},{"id":"macro-yr3d5pt","name":"Yeni Makro","description":"Kullanıcı tanımlı makro","enabled":true,"triggerKey":"KEY_A","triggerMode":"ONCE","repeatCount":1,"actions":[{"id":"act-1","type":"KEY_TAP","key":"KEY_X","delayMs":20},{"id":"act-2","type":"DELAY","delayMs":40,"jitterMs":2},{"id":"act-fe26ncx","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-8i710su","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-93gxpmh","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-ar49xhc","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-6hou3hh","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-arhp3t0","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-dvatjb8","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-y60omil","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-qircjy0","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-tdvknfk","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-up7xewj","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-xrzdr6n","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-rn63mnz","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-8kjt2c4","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-5r2yzwp","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-e8ajn17","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-u6srr2t","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-37r7neq","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-1mka5fl","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-j6j9ypu","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-6fk2ujv","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-q7w6e3j","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-71ltn10","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"}],"tags":["Özel"],"createdAt":1793269706930,"updatedAt":1793269706930}]}"#).unwrap()
    };

    println!("[HAZIR] Yüklenen Profil: {}", profile.name);
    for m in &profile.macros {
        println!("  -> [{}] '{}' (Tetikleyici: {} | Mod: {:?})", if m.enabled { "AKTİF" } else { "KAPALI" }, m.name, m.trigger_key, m.trigger_mode);
    }

    let virtual_device = create_virtual_device(&profile.virtual_device_name);
    let vdev_arc = Arc::new(Mutex::new(virtual_device));
    let pressed_keys_arc = Arc::new(Mutex::new(HashSet::new()));
    let physical_held_keys_arc: Arc<RwLock<HashSet<Key>>> = Arc::new(RwLock::new(HashSet::new()));
    let running_toggles: Arc<Mutex<HashMap<String, Arc<AtomicBool>>>> = Arc::new(Mutex::new(HashMap::new()));
    let double_tap_tracker: Arc<Mutex<HashMap<Key, Instant>>> = Arc::new(Mutex::new(HashMap::new()));

    let (mut devices, mut perm_denied) = discover_devices();
    while devices.is_empty() {
        // Ana GUI kapandıysa bekleme döngüsünden çık
        if unsafe { libc::getppid() } == 1 {
            return;
        }
        if perm_denied > 0 {
            eprintln!("[HATA: İZİN GEREKLİ] /dev/input/event* aygıtlarına okuma izni verilemedi.");
            eprintln!("Arayüzdeki 'Donanım İzinlerini Düzelt' butonuna tıklayın.");
        }
        thread::sleep(Duration::from_millis(1500));
        let (d, p) = discover_devices();
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

    let panic_key_val = string_to_key(&profile.panic_key).unwrap_or(Key::KEY_PAUSE);
    let mut last_scan = Instant::now();

    loop {
        // 1. Ana uygulama kapandıysa makro motoru derhal sonlansın
        if unsafe { libc::getppid() } == 1 {
            println!("[MacroStat Motor] Ana uygulama sonlandırıldı. Motor kapatılıyor.");
            break;
        }

        // 2. Poll ile donanım olaylarını 200ms zaman aşımıyla dinle
        let ret = unsafe {
            libc::poll(
                poll_fds.as_mut_ptr(),
                poll_fds.len() as libc::nfds_t,
                200,
            )
        };

        // 3. Hata veya zaman aşımında aygıtları yeniden tara
        let has_err = poll_fds.iter().any(|pfd| pfd.revents & (libc::POLLERR | libc::POLLHUP | libc::POLLNVAL) != 0);
        if has_err || last_scan.elapsed() > Duration::from_secs(4) {
            last_scan = Instant::now();
            let (new_devs, _) = discover_devices();
            if !new_devs.is_empty() && (new_devs.len() != devices.len() || has_err) {
                devices = new_devs;
                poll_fds = devices.iter().map(|d| libc::pollfd {
                    fd: d.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                }).collect();
                continue;
            }
        }

        if ret > 0 {
            for (i, pfd) in poll_fds.iter().enumerate() {
                if pfd.revents & libc::POLLIN != 0 {
                    if let Ok(events) = devices[i].fetch_events() {
                        for ev in events {
                            if ev.event_type() == EventType::KEY {
                                let key = Key::new(ev.code());
                                let is_press = ev.value() == 1;
                                let is_release = ev.value() == 0;

                                if is_press {
                                    physical_held_keys_arc.write().unwrap().insert(key);
                                } else if is_release {
                                    physical_held_keys_arc.write().unwrap().remove(&key);
                                }

                                if keys_are_equivalent(key, panic_key_val) && is_press {
                                    println!("\n[STOP] Acil durdurma tetiklendi! Tüm makrolar sonlandırıldı.");
                                    PANIC_STOP.store(true, Ordering::SeqCst);
                                    let mut toggles = running_toggles.lock().unwrap();
                                    for flag in toggles.values() {
                                        flag.store(false, Ordering::SeqCst);
                                    }
                                    toggles.clear();
                                    drop(toggles);

                                    let mut dev = vdev_arc.lock().unwrap();
                                    let mut pressed = pressed_keys_arc.lock().unwrap();
                                    release_all_keys(&mut dev, &mut pressed);
                                    println!("[STOP] Makro motoru durduruldu. Arayüzden yeniden başlatılana kadar makrolar çalışmayacaktır.");
                                    std::process::exit(0);
                                }

                                for m in &profile.macros {
                                    if !m.enabled { continue; }

                                    let trigger_match = if m.trigger_key.contains('+') {
                                        let parts: Vec<&str> = m.trigger_key.split('+').map(|s| s.trim()).collect();
                                        let combo_keys: Vec<Option<Key>> = parts.iter().map(|p| string_to_key(p)).collect();
                                        if combo_keys.iter().all(|k| k.is_some()) {
                                            let keys_vec: Vec<Key> = combo_keys.into_iter().map(|k| k.unwrap()).collect();
                                            let held = physical_held_keys_arc.read().unwrap();
                                            is_press && keys_vec.iter().any(|k| keys_are_equivalent(*k, key)) && keys_vec.iter().all(|k| held.iter().any(|h| keys_are_equivalent(*k, *h)))
                                        } else {
                                            false
                                        }
                                    } else if let Some(t_key) = string_to_key(&m.trigger_key) {
                                        keys_are_equivalent(t_key, key) && is_press
                                    } else {
                                        false
                                    };

                                    if trigger_match {
                                        println!("[MacroStat Tetiklendi] '{}' yürütülüyor (Tetikleyici: {} | Mod: {:?})", m.name, m.trigger_key, m.trigger_mode);
                                        let actions_clone = m.actions.clone();
                                        let vdev_clone = Arc::clone(&vdev_arc);
                                        let pressed_clone = Arc::clone(&pressed_keys_arc);
                                        let mode = m.trigger_mode.clone();
                                        let repeat = m.repeat_count;
                                        let macro_name = m.name.clone();

                                        match mode {
                                            TriggerMode::ONCE => {
                                                println!("[MacroStat Tetiklendi] '{}' yürütülüyor (Tetikleyici: {} | Mod: ONCE)", m.name, m.trigger_key);
                                                thread::spawn(move || {
                                                    execute_macro_actions(&actions_clone, &vdev_clone, &pressed_clone, None);
                                                    println!("[MacroStat Tamamlandı] '{}' başarıyla tamamlandı.", macro_name);
                                                });
                                            }
                                            TriggerMode::REPEAT_COUNT => {
                                                let macro_id_key = if !m.id.is_empty() { m.id.clone() } else { format!("trigger_{}", m.trigger_key) };
                                                let mut toggles = running_toggles.lock().unwrap();
                                                if let Some(flag) = toggles.get(&macro_id_key) {
                                                    if flag.load(Ordering::SeqCst) {
                                                        println!("[TEKRAR DURDURULDU] Tetikleyiciye tekrar basıldı, makro durduruldu: '{}'", m.name);
                                                        flag.store(false, Ordering::SeqCst);
                                                        toggles.remove(&macro_id_key);
                                                        drop(toggles);

                                                        let mut dev = vdev_arc.lock().unwrap();
                                                        let mut pressed = pressed_keys_arc.lock().unwrap();
                                                        release_all_keys(&mut dev, &mut pressed);
                                                        continue;
                                                    }
                                                }
                                                println!("[MacroStat Tetiklendi] '{}' başlatıldı ({} Tekrar)", m.name, repeat);
                                                let flag = Arc::new(AtomicBool::new(true));
                                                toggles.insert(macro_id_key.clone(), Arc::clone(&flag));
                                                drop(toggles);

                                                let flag_clone = Arc::clone(&flag);
                                                let toggles_ref = Arc::clone(&running_toggles);
                                                let key_str = macro_id_key.clone();
                                                let vdev_c = Arc::clone(&vdev_clone);
                                                let pressed_c = Arc::clone(&pressed_keys_arc);
                                                thread::spawn(move || {
                                                    for rep in 0..repeat {
                                                        if PANIC_STOP.load(Ordering::SeqCst) || !flag_clone.load(Ordering::SeqCst) { break; }
                                                        if !execute_macro_actions(&actions_clone, &vdev_c, &pressed_c, Some(&flag_clone)) {
                                                            break;
                                                        }
                                                        println!("[MacroStat Tekrar {}/{}] '{}'", rep + 1, repeat, macro_name);
                                                    }
                                                    flag_clone.store(false, Ordering::SeqCst);
                                                    let mut t = toggles_ref.lock().unwrap();
                                                    t.remove(&key_str);
                                                    drop(t);
                                                    let mut dev = vdev_c.lock().unwrap();
                                                    let mut pressed = pressed_c.lock().unwrap();
                                                    release_all_keys(&mut dev, &mut pressed);
                                                    println!("[MacroStat Tamamlandı] '{}' tüm tekrarlar tamamlandı.", macro_name);
                                                });
                                            }
                                            TriggerMode::TOGGLE_LOOP => {
                                                let macro_id_key = if !m.id.is_empty() { m.id.clone() } else { format!("trigger_{}", m.trigger_key) };
                                                let mut toggles = running_toggles.lock().unwrap();
                                                if let Some(flag) = toggles.get(&macro_id_key) {
                                                    if flag.load(Ordering::SeqCst) {
                                                        println!("[DÖNGÜ KAPATILDI] Tetikleyiciye tekrar basıldı, makro durduruldu: '{}'", m.name);
                                                        flag.store(false, Ordering::SeqCst);
                                                        toggles.remove(&macro_id_key);
                                                        drop(toggles);

                                                        let mut dev = vdev_arc.lock().unwrap();
                                                        let mut pressed = pressed_keys_arc.lock().unwrap();
                                                        release_all_keys(&mut dev, &mut pressed);
                                                        continue;
                                                    }
                                                }
                                                println!("[DÖNGÜ BAŞLATILDI] Makro: '{}'", m.name);
                                                let flag = Arc::new(AtomicBool::new(true));
                                                toggles.insert(macro_id_key.clone(), Arc::clone(&flag));
                                                drop(toggles);

                                                let flag_clone = Arc::clone(&flag);
                                                let name_clone = m.name.clone();
                                                let toggles_ref = Arc::clone(&running_toggles);
                                                let key_str = macro_id_key.clone();
                                                let vdev_c = Arc::clone(&vdev_clone);
                                                let pressed_c = Arc::clone(&pressed_keys_arc);
                                                thread::spawn(move || {
                                                    while flag_clone.load(Ordering::SeqCst) && !PANIC_STOP.load(Ordering::SeqCst) {
                                                        if !execute_macro_actions(&actions_clone, &vdev_c, &pressed_c, Some(&flag_clone)) {
                                                            break;
                                                        }
                                                        if !flag_clone.load(Ordering::SeqCst) || PANIC_STOP.load(Ordering::SeqCst) {
                                                            break;
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
                                                    println!("[DÖNGÜ SONLANDI] '{}'", name_clone);
                                                });
                                            }
                                            TriggerMode::WHILE_HELD => {
                                                let held_arc_clone = Arc::clone(&physical_held_keys_arc);
                                                let required_keys: Vec<Key> = if m.trigger_key.contains('+') {
                                                    m.trigger_key.split('+').filter_map(|s| string_to_key(s.trim())).collect()
                                                } else {
                                                    string_to_key(&m.trigger_key).into_iter().collect()
                                                };
                                                let name_clone = m.name.clone();
                                                let vdev_c = Arc::clone(&vdev_clone);
                                                let pressed_c = Arc::clone(&pressed_clone);
                                                let stop_flag = Arc::new(AtomicBool::new(true));
                                                let stop_flag_c = Arc::clone(&stop_flag);

                                                thread::spawn(move || {
                                                    while !PANIC_STOP.load(Ordering::SeqCst) && stop_flag_c.load(Ordering::SeqCst) {
                                                        {
                                                            let held = held_arc_clone.read().unwrap();
                                                            if !required_keys.iter().all(|k| held.iter().any(|h| keys_are_equivalent(*k, *h))) {
                                                                break;
                                                            }
                                                        }
                                                        if !execute_macro_actions(&actions_clone, &vdev_c, &pressed_c, Some(&stop_flag_c)) {
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
                                                    println!("[BASILI TUTMA BIRAKILDI] '{}' durduruldu.", name_clone);
                                                });
                                            }
                                            TriggerMode::DOUBLE_TAP => {
                                                let now = Instant::now();
                                                let mut tracker = double_tap_tracker.lock().unwrap();
                                                let window_ms = m.double_tap_timeout_ms;
                                                let is_double = if let Some(last_time) = tracker.get(&key) {
                                                    last_time.elapsed() <= Duration::from_millis(window_ms)
                                                } else {
                                                    false
                                                };

                                                if is_double {
                                                    tracker.remove(&key);
                                                    drop(tracker);
                                                    println!("[ÇİFT DOKUNMA] '{}' yürütülüyor (Pencere: {}ms)", m.name, window_ms);
                                                    thread::spawn(move || {
                                                        execute_macro_actions(&actions_clone, &vdev_clone, &pressed_clone, None);
                                                        println!("[MacroStat Tamamlandı] '{}' çift dokunma tamamlandı.", macro_name);
                                                    });
                                                } else {
                                                    tracker.insert(key, now);
                                                }
                                            }
                                            TriggerMode::HOLD_LONG_PRESS => {
                                                let held_c = Arc::clone(&physical_held_keys_arc);
                                                let hold_ms = m.hold_duration_ms;
                                                thread::spawn(move || {
                                                    thread::sleep(Duration::from_millis(hold_ms));
                                                    if PANIC_STOP.load(Ordering::SeqCst) { return; }
                                                    let is_still_held = held_c.read().unwrap().contains(&key);
                                                    if is_still_held {
                                                        println!("[UZUN BASIM] '{}' yürütülüyor (Eşik: {}ms)", macro_name, hold_ms);
                                                        execute_macro_actions(&actions_clone, &vdev_clone, &pressed_clone, None);
                                                        println!("[MacroStat Tamamlandı] '{}' uzun basım tamamlandı.", macro_name);
                                                    }
                                                });
                                            }
                                            TriggerMode::PRESS_AND_RELEASE => {
                                                println!("[ÇİFT EYLEM: BASILDI] '{}' yürütülüyor", m.name);
                                                thread::spawn(move || {
                                                    execute_macro_actions(&actions_clone, &vdev_clone, &pressed_clone, None);
                                                });
                                            }
                                        }
                                    }
                                }

                                if is_release {
                                    for m in &profile.macros {
                                        if !m.enabled || m.trigger_mode != TriggerMode::PRESS_AND_RELEASE { continue; }
                                        let trigger_matches = if let Some(t_key) = string_to_key(&m.trigger_key) {
                                            keys_are_equivalent(t_key, key)
                                        } else {
                                            false
                                        };
                                        if trigger_matches && !m.release_actions.is_empty() {
                                            println!("[ÇİFT EYLEM: BIRAKILDI] '{}' bırakış eylemleri yürütülüyor", m.name);
                                            let release_clone = m.release_actions.clone();
                                            let vdev_c = Arc::clone(&vdev_arc);
                                            let pressed_c = Arc::clone(&pressed_keys_arc);
                                            thread::spawn(move || {
                                                execute_macro_actions(&release_clone, &vdev_c, &pressed_c, None);
                                            });
                                        }
                                    }
                                }
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
}

EOF

cat << 'EOF' > cachymacro/profile.json
{
  "id": "profile-cachy-default",
  "name": "MacroStat Varsayılan Profil",
  "description": "CachyOS & KDE Plasma için donanım tabanlı sıfır gecikmeli makrolar",
  "panicKey": "KEY_PAUSE",
  "virtualDeviceName": "MacroStat Virtual Engine",
  "defaultJitterMs": 2,
  "macros": [
    {
      "id": "macro-turbo-shift-ctrl",
      "name": "Shift+Ctrl Çift Tuş Tetikleyici",
      "description": "LeftShift + LeftCtrl kombinasyonuna basıldığında hızlı X tuşu tetikler.",
      "enabled": true,
      "triggerKey": "KEY_LEFTSHIFT+KEY_LEFTCTRL",
      "triggerMode": "ONCE",
      "repeatCount": 1,
      "tags": [
        "Kombinasyon",
        "Oyun"
      ],
      "actions": [
        {
          "id": "a1",
          "type": "KEY_DOWN",
          "key": "KEY_X",
          "description": "X tuşuna basılı tut"
        },
        {
          "id": "a2",
          "type": "DELAY",
          "delayMs": 40,
          "jitterMs": 2,
          "description": "40ms bekle"
        },
        {
          "id": "a3",
          "type": "KEY_UP",
          "key": "KEY_X",
          "description": "X tuşunu bırak"
        }
      ],
      "createdAt": 1793259933773,
      "updatedAt": 1793259933773
    },
    {
      "id": "macro-burst-clicker",
      "name": "Mouse 5 Hızlı Tıklama",
      "description": "Fare yan tuşuna (M5) basıldığında sol tık bas-çek yapar.",
      "enabled": true,
      "triggerKey": "BTN_EXTRA",
      "triggerMode": "ONCE",
      "repeatCount": 1,
      "tags": [
        "Fare",
        "FPS"
      ],
      "actions": [
        {
          "id": "m1",
          "type": "MOUSE_DOWN",
          "mouseButton": "LEFT",
          "description": "Sol fare tuşuna bas"
        },
        {
          "id": "m2",
          "type": "DELAY",
          "delayMs": 25,
          "jitterMs": 2,
          "description": "25ms bekle"
        },
        {
          "id": "m3",
          "type": "MOUSE_UP",
          "mouseButton": "LEFT",
          "description": "Sol fareyi bırak"
        }
      ],
      "createdAt": 1793256333773,
      "updatedAt": 1793256333773
    },
    {
      "id": "macro-fast-macro",
      "name": "F8 Seri Metin & Enter",
      "description": "F8 tuşuyla hızlı terminal komutunu enjekte eder.",
      "enabled": true,
      "triggerKey": "KEY_F8",
      "triggerMode": "ONCE",
      "repeatCount": 1,
      "tags": [
        "Otomasyon",
        "Terminal"
      ],
      "actions": [
        {
          "id": "t1",
          "type": "TEXT",
          "text": "uname -r",
          "description": "Metin yazdır"
        },
        {
          "id": "t2",
          "type": "DELAY",
          "delayMs": 30,
          "jitterMs": 1,
          "description": "30ms bekle"
        },
        {
          "id": "t3",
          "type": "KEY_TAP",
          "key": "KEY_ENTER",
          "description": "Enter tuşuna bas"
        }
      ],
      "createdAt": 1793252733773,
      "updatedAt": 1793252733773
    },
    {
      "id": "macro-yr3d5pt",
      "name": "Yeni Makro",
      "description": "Kullanıcı tanımlı makro",
      "enabled": true,
      "triggerKey": "KEY_A",
      "triggerMode": "ONCE",
      "repeatCount": 1,
      "actions": [
        {
          "id": "act-1",
          "type": "KEY_TAP",
          "key": "KEY_X",
          "delayMs": 20
        },
        {
          "id": "act-2",
          "type": "DELAY",
          "delayMs": 40,
          "jitterMs": 2
        },
        {
          "id": "act-fe26ncx",
          "type": "TEXT",
          "delayMs": 20,
          "jitterMs": 2,
          "text": "Selam CachyOS!"
        },
        {
          "id": "act-8i710su",
          "type": "TEXT",
          "delayMs": 20,
          "jitterMs": 2,
          "text": "Selam CachyOS!"
        },
        {
          "id": "act-93gxpmh",
          "type": "TEXT",
          "delayMs": 20,
          "jitterMs": 2,
          "text": "Selam CachyOS!"
        },
        {
          "id": "act-ar49xhc",
          "type": "TEXT",
          "delayMs": 20,
          "jitterMs": 2,
          "text": "Selam CachyOS!"
        },
        {
          "id": "act-6hou3hh",
          "type": "TEXT",
          "delayMs": 20,
          "jitterMs": 2,
          "text": "Selam CachyOS!"
        },
        {
          "id": "act-arhp3t0",
          "type": "TEXT",
          "delayMs": 20,
          "jitterMs": 2,
          "text": "Selam CachyOS!"
        },
        {
          "id": "act-dvatjb8",
          "type": "TEXT",
          "delayMs": 20,
          "jitterMs": 2,
          "text": "Selam CachyOS!"
        },
        {
          "id": "act-y60omil",
          "type": "TEXT",
          "delayMs": 20,
          "jitterMs": 2,
          "text": "Selam CachyOS!"
        },
        {
          "id": "act-qircjy0",
          "type": "TEXT",
          "delayMs": 20,
          "jitterMs": 2,
          "text": "Selam CachyOS!"
        },
        {
          "id": "act-tdvknfk",
          "type": "TEXT",
          "delayMs": 20,
          "jitterMs": 2,
          "text": "Selam CachyOS!"
        },
        {
          "id": "act-up7xewj",
          "type": "TEXT",
          "delayMs": 20,
          "jitterMs": 2,
          "text": "Selam CachyOS!"
        },
        {
          "id": "act-xrzdr6n",
          "type": "TEXT",
          "delayMs": 20,
          "jitterMs": 2,
          "text": "Selam CachyOS!"
        },
        {
          "id": "act-rn63mnz",
          "type": "TEXT",
          "delayMs": 20,
          "jitterMs": 2,
          "text": "Selam CachyOS!"
        },
        {
          "id": "act-8kjt2c4",
          "type": "TEXT",
          "delayMs": 20,
          "jitterMs": 2,
          "text": "Selam CachyOS!"
        },
        {
          "id": "act-5r2yzwp",
          "type": "TEXT",
          "delayMs": 20,
          "jitterMs": 2,
          "text": "Selam CachyOS!"
        },
        {
          "id": "act-e8ajn17",
          "type": "TEXT",
          "delayMs": 20,
          "jitterMs": 2,
          "text": "Selam CachyOS!"
        },
        {
          "id": "act-u6srr2t",
          "type": "TEXT",
          "delayMs": 20,
          "jitterMs": 2,
          "text": "Selam CachyOS!"
        },
        {
          "id": "act-37r7neq",
          "type": "TEXT",
          "delayMs": 20,
          "jitterMs": 2,
          "text": "Selam CachyOS!"
        },
        {
          "id": "act-1mka5fl",
          "type": "TEXT",
          "delayMs": 20,
          "jitterMs": 2,
          "text": "Selam CachyOS!"
        },
        {
          "id": "act-j6j9ypu",
          "type": "TEXT",
          "delayMs": 20,
          "jitterMs": 2,
          "text": "Selam CachyOS!"
        },
        {
          "id": "act-6fk2ujv",
          "type": "TEXT",
          "delayMs": 20,
          "jitterMs": 2,
          "text": "Selam CachyOS!"
        },
        {
          "id": "act-q7w6e3j",
          "type": "TEXT",
          "delayMs": 20,
          "jitterMs": 2,
          "text": "Selam CachyOS!"
        },
        {
          "id": "act-71ltn10",
          "type": "TEXT",
          "delayMs": 20,
          "jitterMs": 2,
          "text": "Selam CachyOS!"
        }
      ],
      "tags": [
        "Özel"
      ],
      "createdAt": 1793269706930,
      "updatedAt": 1793269706930
    }
  ]
}
EOF

cat << 'EOF' > cachymacro/KULLANIM_KILAVUZU.md
# MacroStat - Kullanım Kılavuzu ve Sistem Çalışma Mantığı
**Hedef Sistem:** CachyOS (Arch Linux) | KDE Plasma (Wayland & X11)
**Motor Mimarisi:** Rust + Linux Kernel `evdev` & `uinput` (Sıfır Gecikme, %0 CPU, Tamamen Çevrimdışı)
**Masaüstü Arayüzü:** Python 3 + PyQt6 (Native Qt6 Bağımsız Penceresi - Web/Tarayıcı DEĞİL)

---

## 🔍 Makro Tetikleme Tuşuna Basıldığında Neden Çalışmıyordu ve Nasıl Düzeltildi?

Eski sürümde tuşa basıldığında makroların çalışmamasının **3 temel teknik sebebi** tespit edilmiş ve kalıcı olarak düzeltilmiştir:

1. **Wayland / Libinput Sanal Aygıt Sınıflandırma Hatası (Çözüldü):**
   - **Sorun:** Eski kodda sanal uinput aygıtına `1..576` aralığındaki tüm tuş kodları topluca kaydediliyordu. Bu aralık içinde joystick ve gamepad kodları (`BTN_JOYSTICK` [288], `BTN_GAMEPAD` [304]) yer alıyordu. Linux `udev-builtin-input_id` ve KDE Wayland `libinput` kütüphanesi bu aygıtı standart masaüstü klavyesi/faresi yerine **"Oyun Kolu / Joystick"** olarak işaretliyor ve masaüstündeki pencerelere (terminal, metin editörü, oyun vb.) klavye/fare olayı göndermesini engelliyordu.
   - **Düzeltme:** Sanal aygıt saf bir **Masaüstü Klavye (1..248)** ve **Fare (272..279)** olarak izole edildi; hiçbir joystick/gamepad kodu eklenmedi. Artık KDE Plasma (Wayland ve X11) her tuş vuruşunu ve tıklamayı anında kabul eder.

2. **Tuş Eşleme ve Sağ/Sol Tuş Esnekliği (Çözüldü):**
   - **Sorun:** Kullanıcı tetikleyici olarak "Shift", "Ctrl" veya "Alt" tanımladığında motor yalnızca `KEY_LEFTSHIFT` veya `KEY_LEFTCTRL` kodunu bekliyor, sağ taraftaki tuşa basıldığında tetikleyici çalışmıyordu. Ayrıca `MOUSE4`, `M4`, `MOUSE5`, `M5` gibi yan tuş isimlendirmeleri eşleşmiyordu.
   - **Düzeltme:** `keys_are_equivalent` fonksiyonu eklenerek genel Ctrl/Shift/Alt/Meta tanımlarında hem sol hem sağ donanım tuşları desteklendi. Fare yan butonları (`BTN_SIDE`, `BTN_EXTRA`, `MOUSE_4`, `MOUSE_5`) tam eşlendi.

3. **Wayland Zamanlama ve Minimum Gecikme Toleransı (Çözüldü):**
   - **Sorun:** Wayland kompozitörleri (KWin), 5-10 milisaniyeden daha kısa süren sanal bas-çek olaylarını arka arkaya geldiğinde birleştirebiliyor (coalesce) veya düşürebiliyordu.
   - **Düzeltme:** Tuş basma ile bırakma arasına Wayland standartlarına uygun minimum 25ms basılı kalma güvencesi eklendi.

---

## ⚡ Sırasıyla Uygulanması Gereken Komutlar (Adım Adım Çalıştırma)

### 📌 Adım 1: Kurulum Betiğini Çalıştırın
Dosyaları çıkardığınız klasörde şu komutları verin:
```bash
chmod +x install_all.sh
./install_all.sh
```
*Bu komut gerekli CachyOS paketlerini kurar, udev donanım kuralını yazar ve Rust motorunu ultra düşük gecikmeli release modunda derler.*

### 📌 Adım 2: Masaüstü Arayüzünü Başlatın
```bash
./baslat-arayuz.sh
```
*İster ana klasörde ister `cachymacro/` alt klasöründe olun, `./baslat-arayuz.sh` arayüzü ve motoru otomatik başlatır.*

---

## 🛡️ Donanım İzinleri ve Kontroller

1. **"🟢 Aktif" Durumu:** Arayüz açıldığında üst çubukta yeşil renkli **"🟢 Aktif"** rozeti görünmelidir.
2. **"🔴 Motor Durduruldu" Görünüyorsa:**
   - Üst çubuktaki mavi **"🛡️ İzinleri Düzelt & Başlat"** butonuna tıklayın.
   - Polkit yetkilendirmesi açılarak `/dev/uinput` ve `/dev/input/event*` izinleri kullanıcı oturumunuza otomatik tanımlanır ve motor anında başlar.

---

## 🎯 Makroları Test Etme ve Günlük İnceleme

- **F8 Hızlı Metin Testi:** Terminal veya metin düzenleyici açıkken **F8** tuşuna basın. `uname -r` komutunun ve Enter tuşunun otomatik yazıldığını göreceksiniz.
- **Shift+Ctrl Çift Tuş Kombinasyonu:** **LeftShift + LeftCtrl** tuşlarına birlikte bastığınızda tanımlı makro derhal tetiklenir.
- **Mouse 5 (Yan Tuş) Tıklayıcı:** Farenizin yan ileri tuşuna bastığınızda hızlı sol tık simülasyonu çalışır.
- **Canlı Günlüğü İnceleme:** Arayüzün üst çubuğundaki **"📋 Günlük"** butonuna basarak hangi tuşların algılandığını ve makroların ne zaman tetiklendiğini anlık olarak okuyabilirsiniz (`/tmp/cachymacro.log`).

---

## 🔒 Metin Yazdırırken ve Makroları Ayarlarken Durdurma (Otomatik İzolasyon)

Tetikleyici tuş ayarlarken, metin yazdırırken (`TEXT` eylemi) veya makro yapılandırması yaparken klavyenizdeki herhangi bir tuşa bastığınızda başka bir makronun devreye girip çakışmaması için **Otomatik İzolasyon Sistemi** entegre edilmiştir:
- **Makro Düzenleyiciye Girildiğinde & Metin Yazarken:** Arka plandaki Rust makro motoru (`cachymacro-daemon`) geçici olarak tamamen durdurulur (`stop_daemon`).
- **Tuş & Metin Girişi:** Düzenleme esnasında hangi harflere, tuşlara veya kombinasyonlara basarsanız basın hiçbir makro çalıştırılmaz.
- **Düzenlemeden Çıkıldığında:** Ayarları kaydedip makro listesine döndüğünüzde motor güncel profilinizle otomatik olarak yeniden başlatılır.

---

## 🛑 Acil Durdurma Anahtarı (Panic Key: KEY_PAUSE)
Herhangi bir acil durumda klavyenizden **KEY_PAUSE** tuşuna (veya arayüzdeki büyük kırmızı **🛑 STOP** butonuna) bastığınız anda:
- Tüm makrolar anında durdurulur ve basılı kalan tüm sanal klavye/fare tuşları serbest bırakılır.
- **Kritik Güvenlik İlkesi:** STOP tuşuna basıldığında motor arayüzden **"🔄 Yeniden Başlat"** butonuna basılana dek **KAPALI KALIR**; hiçbir makro çalıştırılmaz.
- Üst çubukta kırmızı harflerle **DURDURULDU** uyarısı yanar.

---

## 🛡️ Çoklu Profil Yönetimi ve Katı Profil İzolasyonu (Profil 1 vs Profil 2)

Sistem artık çoklu profil desteğine ve katı donanım düzeyinde izolasyona sahiptir:
- **Profil İzolasyon Garantisi:** **Profil 1** seçildiğinde, **Profil 2 veya diğer profillerdeki hiçbir makro arka planda dinlenmez ve asla çalıştırılamaz.**
- **Ayrı Tuş Haritaları:** Farklı profiller aynı tetikleyici tuşları kullansalar bile birbirleriyle asla çakışmaz; yalnızca aktif olan profilin kuralları geçerlidir.
- **Kalıcı Çoklu Yapılandırma:** `profile.json` dosyası hem bağımsız tek profili hem de `activeProfileId` içeren çoklu profil kümesini destekler. Arayüzden profil değiştirdiğiniz anda Rust motoru yeni profili anında yükler.

---

## ⚡ Çift Eylemli Tetikleyiciler (Dual-Action Triggers)

Oyunlarda ve masaüstü otomasyonunda sıradan klavye tuşlarına çift işlev kazandıran mantıklı tetikleme modları eklenmiştir:

1. **✌️ Çift Dokunma (Double-Tap):**
   - Tuşa belirlenen zaman penceresinde (örn. 300 ms) 2 kez seri basıldığında makro tetiklenir.
   - *Örnek:* Normal 'W' tuşuna bir kez basıldığında standart yürüme yapılır; 'W'ye iki kez hızlı dokunulduğunda depar ve kayma kombosu patlar.
2. **⏳ Uzun Basım (Hold / Long Press):**
   - Tuşa hızlı basıp çekildiğinde normal tuş çalışır; ancak tuşa belirlenen süreden (örn. 300 ms) uzun basılı tutulduğunda özel makro veya kombo devreye girer.
   - *Örnek:* 'E' tuşuna kısa basıldığında kapı açılır; 'E' basılı tutulduğunda ağır yetenek iksiri ve ulti kombosu devreye girer.
3. **🎭 Basarken & Bırakırken Çift Eylem (Press & Release):**
   - Tuşa basıldığı anda (Key Down) 1. eylem sırası, tuş serbest bırakıldığı anda (Key Up) 2. eylem sırası otomatik icra edilir.
   - *Örnek (Sniper):* Farenin yan tuşuna basarken dürbün açılıp nefes tutulur (`Shift`); parmak çekildiği anda nefes bırakılır ve otomatik 1. silaha dönülür.

---

## 🔁 Tetikleyici Tuşa Tekrar Basıldığında Makroyu Durdurma (Aç/Kapa & Tekrar Modu)

Döngüsel makrolarda (`TOGGLE_LOOP`) veya tekrarlayan eylemlerde (`REPEAT_COUNT`), makroyu başlatan **tetikleyici tuşa ikinci kez basıldığında**:
- Rust motoru atomik bayrağı (`AtomicBool`) derhal `false` durumuna çeker.
- Eylemler arasındaki mikro gecikmeler (`cancellable_sleep`) **4 milisaniyeden kısa sürede** uyanarak eylemi derhal yarıda keser.
- Makro tarafından basılmış olabilecek tüm sanal klavye ve fare tuşları (`release_all_keys`) temizlenir, hiçbir tuş basılı takılı kalmaz.
- Terminal veya günlüğe `[DÖNGÜ KAPATILDI] Tetikleyiciye tekrar basıldı, makro durduruldu` kaydı düşülür.

---

## 📦 AppImage Olarak Kutudan Çıktığı Gibi Çalıştırma

Tüm sistemi bağımsız, taşınabilir bir **AppImage** paketi olarak derleyip tek dosyayla çalıştırmak için:
```bash
chmod +x build_appimage.sh
./build_appimage.sh
```
- Bu komut Rust motorunu derler, PyQt6 bağımlılıklarını hazırlar ve `MacroStat-x86_64.AppImage` dosyasını üretir.
- **Kutudan Çıktığı Gibi Çalışma:** AppImage çift tıklandığında donanım izinlerini (`/dev/uinput`) denetler, kullanıcı profilini kalıcı olarak `~/.config/cachymacro/profile.json` konumuna yazar ve masaüstü kısayolunu sağlar.

---

## 🚪 Güvenli Kapatma Garantisi
Uygulama penceresini kapattığınızda:
- Linux çekirdeği `PR_SET_PDEATHSIG` ve PyQt6 `closeEvent` kancaları devreye girer.
- Arka plandaki Rust makro motoru (`cachymacro-daemon`) hiçbir yetim (zombie) süreç bırakmadan **TAMAMEN KAPANIR**.

EOF

cat << 'EOF' > cachymacro/gui.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MacroStat - Linux Native GUI (PyQt6)
Wayland & X11 Destekli Makro ve Donanım Otomasyon Stüdyosu
"""

import sys
import os
import json
import time
import subprocess
import shutil
import atexit
import signal
from pathlib import Path

DAEMON_PROC = None

def cleanup_daemon():
    global DAEMON_PROC
    if DAEMON_PROC is not None:
        try:
            if hasattr(os, "killpg"):
                os.killpg(os.getpgid(DAEMON_PROC.pid), signal.SIGKILL)
            else:
                DAEMON_PROC.kill()
        except Exception:
            try:
                DAEMON_PROC.kill()
            except Exception:
                pass
        DAEMON_PROC = None

    try:
        subprocess.run(["pkill", "-9", "-f", "cachymacro-daemon"], stderr=subprocess.DEVNULL)
    except Exception:
        pass
    try:
        subprocess.run(["pkill", "-9", "-f", "cachymacro"], stderr=subprocess.DEVNULL)
    except Exception:
        pass

atexit.register(cleanup_daemon)
signal.signal(signal.SIGINT, lambda sig, frame: (cleanup_daemon(), sys.exit(0)))
signal.signal(signal.SIGTERM, lambda sig, frame: (cleanup_daemon(), sys.exit(0)))
if hasattr(signal, "SIGHUP"):
    signal.signal(signal.SIGHUP, lambda sig, frame: (cleanup_daemon(), sys.exit(0)))

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QTableWidget, QTableWidgetItem, QPushButton, QLabel, QLineEdit,
        QComboBox, QSpinBox, QDoubleSpinBox, QHeaderView, QMessageBox,
        QTabWidget, QGroupBox, QFormLayout, QTextEdit, QDialog, QAbstractItemView,
        QFrame, QInputDialog
    )
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRectF, QPropertyAnimation, pyqtProperty
    from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QPen, QKeySequence
except ImportError:
    print("[HATA] PyQt6 kütüphanesi eksik!")
    print("Kurulum için: sudo pacman -S python-pyqt6")
    sys.exit(1)

# Sabit yollar
SCRIPT_DIR = Path(__file__).resolve().parent
LOG_FILE = Path("/tmp/cachymacro.log")
PANIC_KEY = "KEY_PAUSE"

def locate_paths():
    candidates_bin = [
        SCRIPT_DIR / "cachymacro-daemon",
        SCRIPT_DIR / "target" / "release" / "cachymacro-daemon",
        SCRIPT_DIR / "cachymacro" / "target" / "release" / "cachymacro-daemon",
        SCRIPT_DIR / "cachymacro" / "cachymacro-daemon",
        SCRIPT_DIR.parent / "target" / "release" / "cachymacro-daemon",
        SCRIPT_DIR.parent / "cachymacro" / "target" / "release" / "cachymacro-daemon",
        SCRIPT_DIR.parent / "cachymacro-daemon",
        SCRIPT_DIR / "target" / "debug" / "cachymacro-daemon",
        SCRIPT_DIR / "cachymacro" / "target" / "debug" / "cachymacro-daemon",
        SCRIPT_DIR.parent / "target" / "debug" / "cachymacro-daemon",
        Path.home() / ".cargo" / "bin" / "cachymacro-daemon",
        Path("/usr/local/bin/cachymacro-daemon"),
        Path("/usr/bin/cachymacro-daemon"),
    ]
    which_bin = shutil.which("cachymacro-daemon")
    if which_bin:
        candidates_bin.insert(0, Path(which_bin))

    daemon_bin = None
    for p in candidates_bin:
        if p.exists() and p.is_file():
            try:
                os.chmod(p, 0o755)
            except Exception:
                pass
            daemon_bin = p
            break

    # Bulunamazsa SCRIPT_DIR ve üst dizinde özyinelemeli ara
    if not daemon_bin:
        for root_p in (SCRIPT_DIR, SCRIPT_DIR.parent):
            try:
                for found in root_p.glob("**/cachymacro-daemon"):
                    if found.is_file() and not found.is_symlink() and "src" not in found.parts:
                        try:
                            os.chmod(found, 0o755)
                        except Exception:
                            pass
                        daemon_bin = found
                        break
            except Exception:
                pass
            if daemon_bin:
                break

    user_config_prof = Path.home() / ".config" / "cachymacro" / "profile.json"
    candidates_prof = [
        user_config_prof,
        SCRIPT_DIR / "profile.json",
        SCRIPT_DIR / "cachymacro" / "profile.json",
        SCRIPT_DIR.parent / "profile.json",
        SCRIPT_DIR.parent / "cachymacro" / "profile.json"
    ]
    profile_path = user_config_prof
    for p in candidates_prof:
        if p.exists() and p.is_file():
            profile_path = p
            break

    return daemon_bin, profile_path

DAEMON_BIN, PROFILE_PATH = locate_paths()

class SlidingSwitch(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, parent=None, checked=False):
        super().__init__(parent)
        self.setFixedSize(48, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._checked = checked
        self._position = 26.0 if checked else 2.0
        self.anim = QPropertyAnimation(self, b"position", self)
        self.anim.setDuration(160)

    @pyqtProperty(float)
    def position(self):
        return self._position

    @position.setter
    def position(self, pos):
        self._position = pos
        self.update()

    def isChecked(self):
        return self._checked

    def setChecked(self, checked):
        if self._checked != checked:
            self._checked = checked
            self.anim.stop()
            self.anim.setStartValue(self._position)
            self.anim.setEndValue(26.0 if checked else 2.0)
            self.anim.start()
            self.toggled.emit(self._checked)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg_color = QColor("#10b981") if self._checked else QColor("#334155")
        border_color = QColor("#059669") if self._checked else QColor("#475569")

        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 12, 12)

        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(self._position, 2.0, 20.0, 20.0))

class KeyCaptureDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎯 Tetikleyici Tuş veya İkili Kombinasyon Ayarla")
        self.setFixedSize(480, 280)
        self.captured_key = None
        self.held_keys = []

        # Ana uygulama referansını bul
        self.app_ref = parent if (parent and hasattr(parent, "is_daemon_running")) else None
        if not self.app_ref and parent and hasattr(parent, "window") and hasattr(parent.window(), "is_daemon_running"):
            self.app_ref = parent.window()

        self.was_daemon_running = False
        # Tetikleyici tuş ayarlanırken diğer makroların araya girmesini engellemek için motoru durdur
        if self.app_ref and hasattr(self.app_ref, "is_daemon_running"):
            self.was_daemon_running = self.app_ref.is_daemon_running()
            if self.was_daemon_running:
                self.app_ref.stop_daemon()
                if hasattr(self.app_ref, "show_autosave_banner"):
                    self.app_ref.show_autosave_banner("🛑 Tuş ayarlanırken makrolar durduruldu.")

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Makroların Durdurulduğunu Gösteren Güvenlik Rozeti
        iso_banner = QFrame()
        iso_banner.setStyleSheet("background-color: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; border-radius: 8px; padding: 6px 12px;")
        iso_layout = QHBoxLayout(iso_banner)
        iso_layout.setContentsMargins(4, 2, 4, 2)
        lbl_iso = QLabel("🛑 Makrolar Durduruldu: Tuş ayarlarken diğer makrolar çalıştırılmaz.")
        lbl_iso.setStyleSheet("color: #f87171; font-size: 11px; font-weight: bold;")
        iso_layout.addWidget(lbl_iso)
        layout.addWidget(iso_banner)

        info = QLabel("Klavyenizden bir tuşa basın veya LeftShift+LeftCtrl gibi iki tuşa aynı anda basın:")
        info.setWordWrap(True)
        info.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        layout.addWidget(info)

        self.box = QFrame()
        self.box.setStyleSheet("background-color: #090d16; border: 2px dashed #0284c7; border-radius: 10px; padding: 14px;")
        box_layout = QVBoxLayout(self.box)

        self.status_label = QLabel("⏳ Tuşa veya ikili kombinasyona basın...")
        self.status_label.setStyleSheet("color: #38bdf8; font-size: 15px; font-weight: bold;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box_layout.addWidget(self.status_label)
        layout.addWidget(self.box)

        btn_row = QHBoxLayout()
        self.btn_confirm = QPushButton("✔ Bu Tuşu / Kombinasyonu Kullan")
        self.btn_confirm.setStyleSheet("background-color: #10b981; color: #022c22; font-weight: bold; font-size: 13px; padding: 8px 16px; border-radius: 6px;")
        self.btn_confirm.clicked.connect(self.accept)
        self.btn_confirm.setEnabled(False)
        btn_row.addWidget(self.btn_confirm)

        cancel_btn = QPushButton("İptal")
        cancel_btn.setStyleSheet("background-color: #334155; color: #f1f5f9; padding: 8px 14px; border-radius: 6px;")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()

    def done(self, r):
        # Pencere kapandığında (Kabul, İptal veya X ile kapatma) motor önceden çalışıyorsa yeniden başlat
        if self.was_daemon_running and self.app_ref and hasattr(self.app_ref, "restart_daemon"):
            self.app_ref.restart_daemon(show_message=False)
            if hasattr(self.app_ref, "show_autosave_banner"):
                self.app_ref.show_autosave_banner("▶ Makro motoru tekrar aktif edildi.")
        super().done(r)

    def keyPressEvent(self, event):
        qt_key = event.key()
        if qt_key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.captured_key:
                self.accept()
                return

        if qt_key == Qt.Key.Key_Escape:
            if not self.held_keys:
                self.captured_key = "KEY_ESC"
                self.status_label.setText("✔ Algılandı: KEY_ESC")
                self.status_label.setStyleSheet("color: #10b981; font-size: 15px; font-weight: bold;")
                self.btn_confirm.setText("✔ Bu Tuşu Kullan (KEY_ESC)")
                self.btn_confirm.setEnabled(True)
                return

        key_name = self.map_qt_key_to_evdev(qt_key, event.text())
        if key_name and key_name not in self.held_keys:
            self.held_keys.append(key_name)
            if len(self.held_keys) > 2:
                self.held_keys = self.held_keys[-2:]

        if self.held_keys:
            combo_str = "+".join(self.held_keys)
            self.captured_key = combo_str

            if len(self.held_keys) >= 2:
                self.status_label.setText(f"✔ İkili Kombinasyon: {combo_str}")
                self.status_label.setStyleSheet("color: #10b981; font-size: 16px; font-weight: bold;")
            else:
                self.status_label.setText(f"✔ Algılandı: {combo_str}")
                self.status_label.setStyleSheet("color: #38bdf8; font-size: 16px; font-weight: bold;")

            self.btn_confirm.setText(f"✔ Bu Tuşu Kullan ({combo_str})")
            self.btn_confirm.setEnabled(True)

    def keyReleaseEvent(self, event):
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event):
        btn = event.button()
        key_name = None
        if btn == Qt.MouseButton.LeftButton: key_name = "BTN_LEFT"
        elif btn == Qt.MouseButton.RightButton: key_name = "BTN_RIGHT"
        elif btn == Qt.MouseButton.MiddleButton: key_name = "BTN_MIDDLE"
        elif btn == Qt.MouseButton.BackButton or btn == Qt.MouseButton.XButton1: key_name = "BTN_SIDE"
        elif btn == Qt.MouseButton.ForwardButton or btn == Qt.MouseButton.XButton2: key_name = "BTN_EXTRA"

        if key_name:
            if key_name not in self.held_keys:
                self.held_keys.append(key_name)
                if len(self.held_keys) > 2:
                    self.held_keys = self.held_keys[-2:]
            combo_str = "+".join(self.held_keys)
            self.captured_key = combo_str
            self.status_label.setText(f"✔ Algılandı: {combo_str}")
            self.status_label.setStyleSheet("color: #10b981; font-size: 16px; font-weight: bold;")
            self.btn_confirm.setText(f"✔ Bu Tuşu Kullan ({combo_str})")
            self.btn_confirm.setEnabled(True)

    def map_qt_key_to_evdev(self, qt_key, text):
        if Qt.Key.Key_F1 <= qt_key <= Qt.Key.Key_F12:
            return f"KEY_F{qt_key - Qt.Key.Key_F1 + 1}"
        if Qt.Key.Key_A <= qt_key <= Qt.Key.Key_Z:
            return f"KEY_{chr(qt_key)}"
        if Qt.Key.Key_0 <= qt_key <= Qt.Key.Key_9:
            return f"KEY_{chr(qt_key)}"
        mapping = {
            Qt.Key.Key_Space: "KEY_SPACE",
            Qt.Key.Key_Return: "KEY_ENTER",
            Qt.Key.Key_Enter: "KEY_ENTER",
            Qt.Key.Key_Escape: "KEY_ESC",
            Qt.Key.Key_Backspace: "KEY_BACKSPACE",
            Qt.Key.Key_Tab: "KEY_TAB",
            Qt.Key.Key_Shift: "KEY_LEFTSHIFT",
            Qt.Key.Key_Control: "KEY_LEFTCTRL",
            Qt.Key.Key_Alt: "KEY_LEFTALT",
            Qt.Key.Key_Meta: "KEY_LEFTMETA",
            Qt.Key.Key_CapsLock: "KEY_CAPSLOCK",
            Qt.Key.Key_Pause: "KEY_PAUSE",
            Qt.Key.Key_Delete: "KEY_DELETE",
        }
        return mapping.get(qt_key, f"KEY_{text.upper()}" if text and text.isalnum() else None)

class MacroStatApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MacroStat")
        self.resize(1000, 680)
        self.setMinimumSize(850, 550)

        self.profile_data = self.load_profile()
        self.selected_macro_idx = 0
        self.recording_active = False
        self.recorded_events = []
        self.last_key_time = 0.0
        self.daemon_proc = None
        self.failed_status_checks = 0
        self.is_manually_stopped = False
        self.was_editor_daemon_running = False

        self.setup_ui()
        self.check_and_auto_start_daemon()

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_daemon_status)
        self.status_timer.start(1500)
        self.update_daemon_status()

    def load_profile(self):
        self.all_profiles = []
        self.active_profile_id = ""
        if PROFILE_PATH.exists():
            try:
                with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("profiles") and isinstance(data["profiles"], list) and len(data["profiles"]) > 0:
                        self.all_profiles = data["profiles"]
                        self.active_profile_id = data.get("activeProfileId", self.all_profiles[0].get("id", ""))
                        for p in self.all_profiles:
                            if p.get("id") == self.active_profile_id:
                                return p
                        return self.all_profiles[0]
                    elif data.get("macros"):
                        self.all_profiles = [data]
                        self.active_profile_id = data.get("id", "profile-cachy")
                        return data
            except Exception as e:
                print(f"[UYARI] profile.json okunamadı: {e}")
        default_p = {
            "id": "profile-cachy-default",
            "name": "MacroStat Varsayılan Profil",
            "panicKey": "KEY_PAUSE",
            "virtualDeviceName": "MacroStat Virtual Engine",
            "defaultJitterMs": 2,
            "macros": [{"id":"macro-turbo-shift-ctrl","name":"Shift+Ctrl Çift Tuş Tetikleyici","description":"LeftShift + LeftCtrl kombinasyonuna basıldığında hızlı X tuşu tetikler.","enabled":true,"triggerKey":"KEY_LEFTSHIFT+KEY_LEFTCTRL","triggerMode":"ONCE","repeatCount":1,"tags":["Kombinasyon","Oyun"],"actions":[{"id":"a1","type":"KEY_DOWN","key":"KEY_X","description":"X tuşuna basılı tut"},{"id":"a2","type":"DELAY","delayMs":40,"jitterMs":2,"description":"40ms bekle"},{"id":"a3","type":"KEY_UP","key":"KEY_X","description":"X tuşunu bırak"}],"createdAt":1793259933773,"updatedAt":1793259933773},{"id":"macro-burst-clicker","name":"Mouse 5 Hızlı Tıklama","description":"Fare yan tuşuna (M5) basıldığında sol tık bas-çek yapar.","enabled":true,"triggerKey":"BTN_EXTRA","triggerMode":"ONCE","repeatCount":1,"tags":["Fare","FPS"],"actions":[{"id":"m1","type":"MOUSE_DOWN","mouseButton":"LEFT","description":"Sol fare tuşuna bas"},{"id":"m2","type":"DELAY","delayMs":25,"jitterMs":2,"description":"25ms bekle"},{"id":"m3","type":"MOUSE_UP","mouseButton":"LEFT","description":"Sol fareyi bırak"}],"createdAt":1793256333773,"updatedAt":1793256333773},{"id":"macro-fast-macro","name":"F8 Seri Metin & Enter","description":"F8 tuşuyla hızlı terminal komutunu enjekte eder.","enabled":true,"triggerKey":"KEY_F8","triggerMode":"ONCE","repeatCount":1,"tags":["Otomasyon","Terminal"],"actions":[{"id":"t1","type":"TEXT","text":"uname -r","description":"Metin yazdır"},{"id":"t2","type":"DELAY","delayMs":30,"jitterMs":1,"description":"30ms bekle"},{"id":"t3","type":"KEY_TAP","key":"KEY_ENTER","description":"Enter tuşuna bas"}],"createdAt":1793252733773,"updatedAt":1793252733773},{"id":"macro-yr3d5pt","name":"Yeni Makro","description":"Kullanıcı tanımlı makro","enabled":true,"triggerKey":"KEY_A","triggerMode":"ONCE","repeatCount":1,"actions":[{"id":"act-1","type":"KEY_TAP","key":"KEY_X","delayMs":20},{"id":"act-2","type":"DELAY","delayMs":40,"jitterMs":2},{"id":"act-fe26ncx","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-8i710su","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-93gxpmh","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-ar49xhc","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-6hou3hh","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-arhp3t0","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-dvatjb8","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-y60omil","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-qircjy0","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-tdvknfk","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-up7xewj","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-xrzdr6n","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-rn63mnz","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-8kjt2c4","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-5r2yzwp","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-e8ajn17","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-u6srr2t","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-37r7neq","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-1mka5fl","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-j6j9ypu","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-6fk2ujv","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-q7w6e3j","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-71ltn10","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"}],"tags":["Özel"],"createdAt":1793269706930,"updatedAt":1793269706930}]
        }
        self.all_profiles = [default_p]
        self.active_profile_id = default_p["id"]
        return default_p

    def save_profile_to_disk(self, restart_daemon=True):
        try:
            self.profile_data["panicKey"] = PANIC_KEY
            # Makro ve eylemlerin geçerli ID ve alanlara sahip olduğundan emin ol
            for m in self.profile_data.get("macros", []):
                if not m.get("id"):
                    m["id"] = f"macro-{int(time.time() * 1000)}"
                for i, act in enumerate(m.get("actions", [])):
                    if not act.get("id"):
                        act["id"] = f"act-{i + 1}"

            # Güncel profili all_profiles içinde güncelle
            found = False
            for idx, p in enumerate(self.all_profiles):
                if p.get("id") == self.profile_data.get("id"):
                    self.all_profiles[idx] = self.profile_data
                    found = True
                    break
            if not found:
                self.all_profiles.append(self.profile_data)

            payload = {
                "activeProfileId": self.profile_data.get("id", ""),
                "profiles": self.all_profiles,
                "id": self.profile_data.get("id", ""),
                "name": self.profile_data.get("name", ""),
                "panicKey": PANIC_KEY,
                "virtualDeviceName": self.profile_data.get("virtualDeviceName", ""),
                "defaultJitterMs": self.profile_data.get("defaultJitterMs", 2),
                "macros": self.profile_data.get("macros", [])
            }

            global PROFILE_PATH
            target_save_path = PROFILE_PATH
            try:
                target_save_path.parent.mkdir(parents=True, exist_ok=True)
                with open(target_save_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
            except OSError:
                target_save_path = Path.home() / ".config" / "cachymacro" / "profile.json"
                target_save_path.parent.mkdir(parents=True, exist_ok=True)
                with open(target_save_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                PROFILE_PATH = target_save_path

            # cachymacro klasörü varsa onun içindeki profile.json'u da senkronize tut
            alt_prof = SCRIPT_DIR / "cachymacro" / "profile.json" if SCRIPT_DIR.name != "cachymacro" else SCRIPT_DIR.parent / "profile.json"
            if alt_prof.parent.exists():
                try:
                    with open(alt_prof, "w", encoding="utf-8") as f:
                        json.dump(payload, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

            if restart_daemon:
                self.restart_daemon(show_message=False)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Profil kaydedilemedi: {e}")
            return False

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Üst Çubuk
        header_frame = QFrame()
        header_frame.setObjectName("headerFrame")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(14, 10, 14, 10)

        title_label = QLabel("MacroStat")
        title_label.setObjectName("appTitle")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: white;")
        header_layout.addWidget(title_label)

        lbl_prof = QLabel("Profil:")
        lbl_prof.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: bold; margin-left: 10px;")
        header_layout.addWidget(lbl_prof)

        self.combo_profiles = QComboBox()
        self.combo_profiles.setStyleSheet("QComboBox { background-color: #1e293b; color: #38bdf8; font-weight: bold; border: 1px solid #0284c7; border-radius: 6px; padding: 4px 8px; min-width: 150px; font-size: 11px; }")
        header_layout.addWidget(self.combo_profiles)

        btn_new_prof = QPushButton("+ Profil")
        btn_new_prof.setStyleSheet("QPushButton { background-color: #0284c7; color: white; font-weight: bold; border-radius: 5px; padding: 4px 8px; font-size: 11px; } QPushButton:hover { background-color: #38bdf8; color: #0f172a; }")
        btn_new_prof.clicked.connect(self.create_new_profile_dialog)
        header_layout.addWidget(btn_new_prof)

        self.populate_profile_combo()
        self.combo_profiles.currentIndexChanged.connect(self.on_profile_selection_changed)

        header_layout.addStretch()

        # STOP çalıştırıldığında üst kısımdaki boşlukta kırmızı harflerle DURDURULDU yazısı
        self.lbl_stopped = QLabel("DURDURULDU")
        self.lbl_stopped.setStyleSheet(
            "color: #ef4444; font-size: 16px; font-weight: 900; letter-spacing: 3px; padding: 3px 18px; "
            "background-color: rgba(239, 68, 68, 0.15); border: 2px solid #ef4444; border-radius: 8px;"
        )
        self.lbl_stopped.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_stopped.hide()
        header_layout.addWidget(self.lbl_stopped)

        header_layout.addStretch()

        self.status_badge = QLabel("● Kontrol ediliyor...")
        self.status_badge.setObjectName("statusBadge")
        header_layout.addWidget(self.status_badge)

        self.btn_quick_fix = QPushButton("🛡️ İzinleri Düzelt & Başlat")
        self.btn_quick_fix.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold; padding: 6px 12px; border-radius: 6px;")
        self.btn_quick_fix.clicked.connect(self.fix_permissions)
        self.btn_quick_fix.hide()
        header_layout.addWidget(self.btn_quick_fix)

        self.btn_view_log = QPushButton("📋 Günlüğü İncele")
        self.btn_view_log.clicked.connect(self.show_daemon_log)
        header_layout.addWidget(self.btn_view_log)

        self.btn_restart_daemon = QPushButton("🔄 Yeniden Başlat")
        self.btn_restart_daemon.clicked.connect(lambda: self.restart_daemon(show_message=True))
        header_layout.addWidget(self.btn_restart_daemon)

        # STOP Butonu + Çark Butonu
        panic_box = QWidget()
        p_layout = QHBoxLayout(panic_box)
        p_layout.setContentsMargins(0, 0, 0, 0)
        p_layout.setSpacing(3)

        self.btn_panic = QPushButton("🛑 STOP")
        self.btn_panic.setStyleSheet("background-color: #dc2626; color: white; font-weight: bold; font-size: 13px; padding: 6px 16px; border-radius: 6px;")
        self.btn_panic.clicked.connect(self.trigger_panic)
        p_layout.addWidget(self.btn_panic)

        self.btn_panic_settings = QPushButton("⚙")
        self.btn_panic_settings.setFixedSize(32, 32)
        self.btn_panic_settings.setStyleSheet("background-color: #334155; color: #f8fafc; border: 1px solid #475569; border-radius: 6px; font-size: 16px; font-weight: bold;")
        self.btn_panic_settings.clicked.connect(self.configure_panic_key)
        p_layout.addWidget(self.btn_panic_settings)

        header_layout.addWidget(panic_box)
        main_layout.addWidget(header_frame)

        # Sekmeler
        self.tabs = QTabWidget()
        self.tab_macros = QWidget()
        self.tab_editor = QWidget()
        self.tab_recorder = QWidget()
        self.tab_system = QWidget()

        self.tabs.addTab(self.tab_macros, "📋 Makrolar")
        self.tabs.addTab(self.tab_editor, "🛠️ Makro Düzenleyici")
        self.tabs.addTab(self.tab_recorder, "🔴 Canlı Tuş Kaydedici")
        self.tabs.addTab(self.tab_system, "⚙️ Sistem & Kılavuz")

        self.setup_macros_tab()
        self.setup_editor_tab()
        self.setup_recorder_tab()
        self.setup_system_tab()

        self.tabs.currentChanged.connect(self.on_tab_changed)
        main_layout.addWidget(self.tabs)

    def populate_profile_combo(self):
        self.combo_profiles.blockSignals(True)
        self.combo_profiles.clear()
        current_idx = 0
        for i, p in enumerate(self.all_profiles):
            self.combo_profiles.addItem(p.get("name", f"Profil {i+1}"), p.get("id"))
            if p.get("id") == self.profile_data.get("id"):
                current_idx = i
        self.combo_profiles.setCurrentIndex(current_idx)
        self.combo_profiles.blockSignals(False)

    def on_profile_selection_changed(self, index):
        if index < 0 or index >= len(self.all_profiles):
            return
        selected_p = self.all_profiles[index]
        self.profile_data = selected_p
        self.active_profile_id = selected_p.get("id")
        self.save_profile_to_disk(restart_daemon=True)
        self.refresh_macro_table()
        self.show_autosave_banner(f"'{selected_p.get('name')}' aktif edildi. Diğer profiller devre dışıdır.")

    def create_new_profile_dialog(self):
        name, ok = QInputDialog.getText(self, "Yeni Profil", "Yeni profil adını girin:")
        if ok and name.strip():
            new_p = {
                "id": f"profile-{int(time.time()*1000)}",
                "name": name.strip(),
                "panicKey": PANIC_KEY,
                "virtualDeviceName": f"{name.strip()} Virtual Engine",
                "defaultJitterMs": 2,
                "macros": []
            }
            self.all_profiles.append(new_p)
            self.profile_data = new_p
            self.active_profile_id = new_p["id"]
            self.populate_profile_combo()
            self.save_profile_to_disk(restart_daemon=True)
            self.refresh_macro_table()
            self.show_autosave_banner(f"'{name.strip()}' profili oluşturuldu ve aktif edildi.")

    def on_tab_changed(self, index):
        if index == 1:
            # Makro düzenlerken ve metin yazarken diğer tüm makrolar durdurulsun
            if self.is_daemon_running() and not getattr(self, "is_manually_stopped", False):
                self.was_editor_daemon_running = True
                self.stop_daemon()
                self.show_autosave_banner("🛑 Düzenleme modu: Metin yazarken ve ayar yaparken makrolar durduruldu.")

            row = self.macro_table.currentRow()
            if 0 <= row < len(self.profile_data.get("macros", [])):
                self.selected_macro_idx = row
            if 0 <= self.selected_macro_idx < len(self.profile_data.get("macros", [])):
                self.load_macro_into_editor(self.selected_macro_idx)
        else:
            # Düzenleyiciden çıkıldığında motoru yeniden başlat (STOP tuşuna basılmamışsa)
            if getattr(self, "was_editor_daemon_running", False) and not getattr(self, "is_manually_stopped", False):
                self.was_editor_daemon_running = False
                self.restart_daemon(show_message=False)
                self.show_autosave_banner("▶ Makro motoru tekrar aktif edildi.")

    def configure_panic_key(self):
        dialog = KeyCaptureDialog(self)
        dialog.setWindowTitle("⚙️ STOP Tuşunu Ayarlayın")
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.captured_key:
            global PANIC_KEY
            PANIC_KEY = dialog.captured_key
            self.show_autosave_banner(f"STOP tuşu '{PANIC_KEY}' olarak güncellendi.")
            self.save_profile_to_disk(restart_daemon=True)

    def show_autosave_banner(self, text):
        self.statusBar().showMessage(f"💾 {text}", 3000)

    # SEKME 1: Makrolar
    def setup_macros_tab(self):
        layout = QVBoxLayout(self.tab_macros)
        layout.setSpacing(10)

        self.macro_table = QTableWidget()
        self.macro_table.setColumnCount(7)
        self.macro_table.setHorizontalHeaderLabels(["Sıra", "Aç / Kapat", "Makro Adı", "Tetikleyici Tuş", "Çalışma Modu", "Eylemler", "Sil"])
        self.macro_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.macro_table.horizontalHeader().resizeSection(0, 95)
        self.macro_table.horizontalHeader().resizeSection(1, 120)
        self.macro_table.horizontalHeader().resizeSection(3, 140)
        self.macro_table.horizontalHeader().resizeSection(4, 130)
        self.macro_table.horizontalHeader().resizeSection(5, 75)
        self.macro_table.horizontalHeader().resizeSection(6, 50)
        self.macro_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.macro_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.macro_table.itemDoubleClicked.connect(self.edit_selected_macro)

        def macro_table_keyPressEvent(event):
            if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self.delete_selected_macro()
                return
            QTableWidget.keyPressEvent(self.macro_table, event)
        self.macro_table.keyPressEvent = macro_table_keyPressEvent

        layout.addWidget(self.macro_table)

        btn_layout = QHBoxLayout()
        self.btn_add_macro = QPushButton("➕ Yeni Makro")
        self.btn_add_macro.clicked.connect(self.create_new_macro)
        btn_layout.addWidget(self.btn_add_macro)

        self.btn_edit_macro = QPushButton("✏️ Düzenle")
        self.btn_edit_macro.clicked.connect(self.edit_selected_macro)
        btn_layout.addWidget(self.btn_edit_macro)

        self.btn_dup_macro = QPushButton("📑 Klonla")
        self.btn_dup_macro.clicked.connect(self.duplicate_selected_macro)
        btn_layout.addWidget(self.btn_dup_macro)

        self.btn_del_macro = QPushButton("✕ Sil (Del)")
        self.btn_del_macro.setStyleSheet("color: #ef4444; font-weight: bold;")
        self.btn_del_macro.clicked.connect(self.delete_selected_macro)
        btn_layout.addWidget(self.btn_del_macro)

        btn_layout.addStretch()

        self.btn_save_all = QPushButton("Kaydet")
        self.btn_save_all.setStyleSheet("background-color: #10b981; color: #022c22; font-weight: bold; padding: 6px 18px; border-radius: 6px;")
        self.btn_save_all.clicked.connect(lambda: self.save_profile_to_disk(restart_daemon=True))
        btn_layout.addWidget(self.btn_save_all)

        layout.addLayout(btn_layout)
        self.refresh_macro_table()

    def refresh_macro_table(self):
        macros = self.profile_data.get("macros", [])
        self.macro_table.setRowCount(len(macros))
        for row, m in enumerate(macros):
            is_active = m.get("enabled", True)

            # Sıra numarası ve hemen yanında yukarı ok, aşağı ok butonları (1 ↑ ↓)
            seq_container = QWidget()
            seq_layout = QHBoxLayout(seq_container)
            seq_layout.setContentsMargins(4, 2, 4, 2)
            seq_layout.setSpacing(4)
            seq_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            lbl_seq = QLabel(str(row + 1))
            lbl_seq.setStyleSheet("font-weight: bold; color: #38bdf8; font-size: 12px; min-width: 14px;")
            seq_layout.addWidget(lbl_seq)

            btn_up = QPushButton("↑")
            btn_up.setFixedSize(22, 22)
            btn_up.setStyleSheet("QPushButton { background-color: #1e293b; color: #38bdf8; border: 1px solid #334155; border-radius: 4px; font-size: 11px; font-weight: bold; } QPushButton:hover { background-color: #0284c7; color: white; }")
            btn_up.setToolTip("Yukarı Taşı (Yukarı Ok)")
            btn_up.setEnabled(row > 0)
            btn_up.clicked.connect(lambda _, r=row: self.move_macro_up_index(r))
            seq_layout.addWidget(btn_up)

            btn_down = QPushButton("↓")
            btn_down.setFixedSize(22, 22)
            btn_down.setStyleSheet("QPushButton { background-color: #1e293b; color: #38bdf8; border: 1px solid #334155; border-radius: 4px; font-size: 11px; font-weight: bold; } QPushButton:hover { background-color: #0284c7; color: white; }")
            btn_down.setToolTip("Aşağı Taşı (Aşağı Ok)")
            btn_down.setEnabled(row < len(macros) - 1)
            btn_down.clicked.connect(lambda _, r=row: self.move_macro_down_index(r))
            seq_layout.addWidget(btn_down)

            self.macro_table.setCellWidget(row, 0, seq_container)

            # Switch
            switch_container = QWidget()
            s_layout = QHBoxLayout(switch_container)
            s_layout.setContentsMargins(6, 2, 6, 2)
            s_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            switch_w = SlidingSwitch(checked=is_active)
            lbl_s = QLabel("AÇIK" if is_active else "KAPALI")
            lbl_s.setStyleSheet("color: #10b981; font-weight: bold; font-size: 11px;" if is_active else "color: #94a3b8; font-size: 11px;")

            def make_toggle(r_idx, label):
                def cb(checked):
                    label.setText("AÇIK" if checked else "KAPALI")
                    label.setStyleSheet("color: #10b981; font-weight: bold; font-size: 11px;" if checked else "color: #94a3b8; font-size: 11px;")
                    self.on_macro_toggle_switch(r_idx, checked)
                return cb

            switch_w.toggled.connect(make_toggle(row, lbl_s))
            s_layout.addWidget(switch_w)
            s_layout.addWidget(lbl_s)
            self.macro_table.setCellWidget(row, 1, switch_container)

            self.macro_table.setItem(row, 2, QTableWidgetItem(m.get("name", "İsimsiz Makro")))
            self.macro_table.setItem(row, 3, QTableWidgetItem(m.get("triggerKey", m.get("trigger_key", ""))))
            self.macro_table.setItem(row, 4, QTableWidgetItem(m.get("triggerMode", m.get("trigger_mode", "ONCE"))))
            self.macro_table.setItem(row, 5, QTableWidgetItem(str(len(m.get("actions", [])))))

            # Kırmızı X (Kırmızı Çarpı) şeklinde silme butonu
            del_container = QWidget()
            del_layout = QHBoxLayout(del_container)
            del_layout.setContentsMargins(4, 2, 4, 2)
            del_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            btn_x = QPushButton("✕")
            btn_x.setFixedSize(26, 24)
            btn_x.setStyleSheet("QPushButton { background-color: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid #ef4444; border-radius: 5px; font-weight: 900; font-size: 14px; } QPushButton:hover { background-color: #dc2626; color: white; }")
            btn_x.setToolTip("Makroyu Sil (Kırmızı X)")
            btn_x.clicked.connect(lambda _, r=row: self.delete_macro_by_index(r))
            del_layout.addWidget(btn_x)
            self.macro_table.setCellWidget(row, 6, del_container)

    def on_macro_toggle_switch(self, row, checked):
        macros = self.profile_data.get("macros", [])
        if 0 <= row < len(macros):
            macros[row]["enabled"] = checked
            self.save_profile_to_disk(restart_daemon=True)

    def move_macro_up_index(self, row):
        macros = self.profile_data.get("macros", [])
        if 1 <= row < len(macros):
            macros[row - 1], macros[row] = macros[row], macros[row - 1]
            self.save_profile_to_disk(restart_daemon=True)
            self.refresh_macro_table()
            self.macro_table.selectRow(row - 1)

    def move_macro_down_index(self, row):
        macros = self.profile_data.get("macros", [])
        if 0 <= row < len(macros) - 1:
            macros[row + 1], macros[row] = macros[row], macros[row + 1]
            self.save_profile_to_disk(restart_daemon=True)
            self.refresh_macro_table()
            self.macro_table.selectRow(row + 1)

    def delete_macro_by_index(self, index):
        macros = self.profile_data.get("macros", [])
        if 0 <= index < len(macros):
            del macros[index]
            self.save_profile_to_disk(restart_daemon=True)
            self.refresh_macro_table()

    def delete_selected_macro(self):
        row = self.macro_table.currentRow()
        if row >= 0:
            self.delete_macro_by_index(row)

    def create_new_macro(self):
        new_m = {
            "id": f"macro-{int(time.time() * 1000)}",
            "name": "Yeni Makro",
            "description": "Kullanıcı tanımlı makro",
            "enabled": True,
            "triggerKey": "KEY_LEFTSHIFT+KEY_LEFTCTRL",
            "triggerMode": "ONCE",
            "repeatCount": 1,
            "actions": [
                {"type": "KEY_TAP", "key": "KEY_X"},
                {"type": "DELAY", "delayMs": 50, "jitterMs": 2}
            ]
        }
        self.profile_data.setdefault("macros", []).append(new_m)
        self.save_profile_to_disk(restart_daemon=True)
        self.selected_macro_idx = len(self.profile_data["macros"]) - 1
        self.refresh_macro_table()
        self.load_macro_into_editor(self.selected_macro_idx)
        self.tabs.setCurrentWidget(self.tab_editor)

    def edit_selected_macro(self):
        row = self.macro_table.currentRow()
        if row >= 0:
            self.selected_macro_idx = row
            self.load_macro_into_editor(row)
            self.tabs.setCurrentWidget(self.tab_editor)

    def duplicate_selected_macro(self):
        row = self.macro_table.currentRow()
        if row >= 0:
            m = dict(self.profile_data["macros"][row])
            m["id"] = f"macro-{int(time.time() * 1000)}"
            m["name"] = m.get("name", "") + " (Kopya)"
            m["triggerKey"] = ""
            m["enabled"] = False
            self.profile_data["macros"].append(m)
            self.save_profile_to_disk(restart_daemon=True)
            self.refresh_macro_table()

    # SEKME 2: Makro Düzenleyici
    def setup_editor_tab(self):
        layout = QVBoxLayout(self.tab_editor)
        layout.setSpacing(10)

        # Düzenleyici Üst Bilgi Rozeti (Makrolar Durduruldu Bildirimi)
        editor_banner = QFrame()
        editor_banner.setStyleSheet("background-color: rgba(14, 165, 233, 0.12); border: 1px solid #0284c7; border-radius: 8px; padding: 7px 12px;")
        eb_layout = QHBoxLayout(editor_banner)
        eb_layout.setContentsMargins(4, 2, 4, 2)
        lbl_eb = QLabel("🛑 Güvenli Düzenleme Modu: Metin yazarken veya makro ayarları yapılırken diğer makrolar durdurulur.")
        lbl_eb.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold;")
        eb_layout.addWidget(lbl_eb)
        layout.addWidget(editor_banner)

        form_group = QGroupBox("Makro Yapılandırması")
        form_layout = QFormLayout(form_group)

        self.edit_name = QLineEdit()
        form_layout.addRow("Makro Adı:", self.edit_name)

        trig_row = QHBoxLayout()
        self.combo_trigger_key = QComboBox()
        self.combo_trigger_key.setEditable(True)
        self.combo_trigger_key.addItems([
            "KEY_LEFTSHIFT+KEY_LEFTCTRL", "KEY_LEFTCTRL+KEY_SPACE", "KEY_LEFTSHIFT+KEY_SPACE",
            "KEY_F1", "KEY_F2", "KEY_F3", "KEY_F4", "KEY_F5", "KEY_F6", "KEY_F7", "KEY_F8",
            "KEY_SPACE", "KEY_X", "KEY_C", "KEY_V", "BTN_SIDE", "BTN_EXTRA"
        ])
        trig_row.addWidget(self.combo_trigger_key)

        btn_capture = QPushButton("🎯 Tuşa / İkili Kombinasyona Basarak Ayarla")
        btn_capture.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold;")
        btn_capture.clicked.connect(self.capture_trigger_key)
        trig_row.addWidget(btn_capture)
        form_layout.addRow("Tetikleyici Tuş:", trig_row)

        self.combo_mode = QComboBox()
        self.combo_mode.addItems([
            "Tek Seferlik (ONCE)",
            "Basılı Tutulduğu Sürece (WHILE_HELD)",
            "Aç / Kapa Döngüsü (TOGGLE_LOOP)",
            "Tekrar Sayısı (REPEAT_COUNT)",
            "Çift Dokunma (DOUBLE_TAP)",
            "Uzun Basım (HOLD_LONG_PRESS)",
            "Bas-Bırak Çift Eylemi (PRESS_AND_RELEASE)"
        ])
        form_layout.addRow("Çalışma Modu:", self.combo_mode)

        self.spin_repeat = QSpinBox()
        self.spin_repeat.setRange(1, 9999)
        self.spin_repeat.setValue(1)
        form_layout.addRow("Tekrar Sayısı:", self.spin_repeat)

        layout.addWidget(form_group)

        # Eylemler Tablosu
        self.action_table = QTableWidget()
        self.action_table.setColumnCount(3)
        self.action_table.setHorizontalHeaderLabels(["Sıra", "Eylem Tipi", "Parametreler"])
        self.action_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.action_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.action_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        # Makro eylemlerini DEL tuşuyla silme desteği
        def action_table_keyPressEvent(event):
            if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self.delete_editor_action()
                return
            QTableWidget.keyPressEvent(self.action_table, event)
        self.action_table.keyPressEvent = action_table_keyPressEvent

        self.action_table.cellDoubleClicked.connect(lambda r, c: self.edit_selected_editor_action())
        layout.addWidget(self.action_table)

        # 1. Sıra Eylem Ekleme Butonları (Klavye & Fare Basılı Tutma / Bırakma Dahil)
        act_row1 = QHBoxLayout()
        btn_add_tap = QPushButton("➕ Tuş Bas-Çek")
        btn_add_tap.setStyleSheet("background-color: #0369a1; color: white; font-weight: bold;")
        btn_add_tap.clicked.connect(lambda: self.add_editor_action("KEY_TAP"))
        act_row1.addWidget(btn_add_tap)

        btn_add_down = QPushButton("➕ Tuşa Bas (Basılı Tut)")
        btn_add_down.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold;")
        btn_add_down.setToolTip("Belirtilen tuşu basılı bırakır (Tuşun basılı kalması)")
        btn_add_down.clicked.connect(lambda: self.add_editor_action("KEY_DOWN"))
        act_row1.addWidget(btn_add_down)

        btn_add_up = QPushButton("➕ Tuşu Bırak")
        btn_add_up.setStyleSheet("background-color: #475569; color: white; font-weight: bold;")
        btn_add_up.setToolTip("Basılı tutulan tuşu serbest bırakır")
        btn_add_up.clicked.connect(lambda: self.add_editor_action("KEY_UP"))
        act_row1.addWidget(btn_add_up)

        btn_add_mclick = QPushButton("➕ Fare Tıkla")
        btn_add_mclick.setStyleSheet("background-color: #b45309; color: white; font-weight: bold;")
        btn_add_mclick.clicked.connect(lambda: self.add_editor_action("MOUSE_CLICK"))
        act_row1.addWidget(btn_add_mclick)

        btn_add_mdown = QPushButton("➕ Fare Basılı Tut")
        btn_add_mdown.setStyleSheet("background-color: #d97706; color: white; font-weight: bold;")
        btn_add_mdown.setToolTip("Fare tuşunu basılı bırakır")
        btn_add_mdown.clicked.connect(lambda: self.add_editor_action("MOUSE_DOWN"))
        act_row1.addWidget(btn_add_mdown)

        btn_add_mup = QPushButton("➕ Fare Bırak")
        btn_add_mup.setStyleSheet("background-color: #78716c; color: white; font-weight: bold;")
        btn_add_mup.setToolTip("Basılı fare tuşunu serbest bırakır")
        btn_add_mup.clicked.connect(lambda: self.add_editor_action("MOUSE_UP"))
        act_row1.addWidget(btn_add_mup)

        layout.addLayout(act_row1)

        # 2. Sıra: Gecikme, Metin, Eylem Düzenleme, Silme ve Kaydetme Butonları
        act_row2 = QHBoxLayout()
        btn_add_del = QPushButton("➕ Gecikme")
        btn_add_del.clicked.connect(lambda: self.add_editor_action("DELAY"))
        act_row2.addWidget(btn_add_del)

        btn_add_text = QPushButton("➕ Metin Yazdır")
        btn_add_text.clicked.connect(lambda: self.add_editor_action("TEXT"))
        act_row2.addWidget(btn_add_text)

        btn_edit_act = QPushButton("🎯 Eylem Tuşunu Ayarla / Düzenle")
        btn_edit_act.setStyleSheet("background-color: #4338ca; color: white; font-weight: bold;")
        btn_edit_act.clicked.connect(self.edit_selected_editor_action)
        act_row2.addWidget(btn_edit_act)

        btn_del_act = QPushButton("❌ Eylemi Sil (Del)")
        btn_del_act.clicked.connect(self.delete_editor_action)
        act_row2.addWidget(btn_del_act)

        btn_clear_all = QPushButton("🗑️ Tüm Eylemleri Sil")
        btn_clear_all.setStyleSheet("color: #f87171; font-weight: bold;")
        btn_clear_all.clicked.connect(self.clear_all_editor_actions)
        act_row2.addWidget(btn_clear_all)

        act_row2.addStretch()

        self.btn_save_macro = QPushButton("Kaydet")
        self.btn_save_macro.setStyleSheet("background-color: #10b981; color: #022c22; font-weight: bold; padding: 6px 20px; font-size: 13px;")
        self.btn_save_macro.clicked.connect(self.save_macro_from_editor)
        act_row2.addWidget(self.btn_save_macro)

        layout.addLayout(act_row2)

    def capture_trigger_key(self):
        dlg = KeyCaptureDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.captured_key:
            self.combo_trigger_key.setEditText(dlg.captured_key)

    def load_macro_into_editor(self, idx):
        macros = self.profile_data.get("macros", [])
        if 0 <= idx < len(macros):
            m = macros[idx]
            self.edit_name.setText(m.get("name", ""))
            self.combo_trigger_key.setEditText(m.get("triggerKey", m.get("trigger_key", "")))
            mode_map = {
                "ONCE": 0,
                "WHILE_HELD": 1,
                "TOGGLE_LOOP": 2,
                "REPEAT_COUNT": 3,
                "DOUBLE_TAP": 4,
                "HOLD_LONG_PRESS": 5,
                "PRESS_AND_RELEASE": 6,
            }
            m_mode = m.get("triggerMode", m.get("trigger_mode", "ONCE"))
            self.combo_mode.setCurrentIndex(mode_map.get(m_mode, 0))
            self.spin_repeat.setValue(int(m.get("repeatCount", m.get("repeat_count", 1))))
            self.current_editing_actions = list(m.get("actions", []))
            self.refresh_editor_actions_table()

    def refresh_editor_actions_table(self):
        actions = getattr(self, "current_editing_actions", [])
        self.action_table.setRowCount(len(actions))
        type_labels = {
            "KEY_TAP": "Tuş Bas-Çek",
            "KEY_DOWN": "Tuşa Bas (Basılı Tut)",
            "KEY_UP": "Tuşu Bırak",
            "MOUSE_CLICK": "Fare Tıkla",
            "MOUSE_DOWN": "Fare Basılı Tut",
            "MOUSE_UP": "Fare Bırak",
            "DELAY": "Gecikme Bekle",
            "TEXT": "Metin Yazdır"
        }
        for i, act in enumerate(actions):
            self.action_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            a_type = act.get("type", "")
            disp_type = type_labels.get(a_type, a_type)
            self.action_table.setItem(i, 1, QTableWidgetItem(disp_type))
            if a_type == "TEXT":
                params = repr(act.get("text", ""))
            elif a_type == "DELAY":
                params = f"{act.get('delayMs', 50)} ms (±{act.get('jitterMs', 2)}ms)"
            elif a_type == "KEY_DOWN":
                params = f"Tuş: {act.get('key', '-')} (Basılı Kalır)"
            elif a_type == "KEY_UP":
                params = f"Tuş: {act.get('key', '-')} (Serbest Bırakılır)"
            elif a_type == "KEY_TAP":
                params = f"Tuş: {act.get('key', '-')} (Basma: {act.get('delayMs', 20)}ms)"
            elif a_type == "MOUSE_DOWN":
                params = f"Fare: {act.get('mouseButton', 'BTN_LEFT')} (Basılı Kalır)"
            elif a_type == "MOUSE_UP":
                params = f"Fare: {act.get('mouseButton', 'BTN_LEFT')} (Serbest Bırakılır)"
            elif a_type == "MOUSE_CLICK":
                params = f"Fare: {act.get('mouseButton', 'BTN_LEFT')}"
            else:
                params = act.get("key") or "-"
            self.action_table.setItem(i, 2, QTableWidgetItem(params))

    def add_editor_action(self, act_type):
        actions = getattr(self, "current_editing_actions", [])
        if act_type in ("KEY_TAP", "KEY_DOWN", "KEY_UP"):
            dlg = KeyCaptureDialog(self)
            dlg.setWindowTitle("Makronun Basacağı Tuşu Seçin (Klavyeden Tuşa Basın)")
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.captured_key:
                selected_key = dlg.captured_key.split("+")[-1]
            else:
                selected_key = "KEY_A"

            if act_type == "KEY_TAP":
                actions.append({"type": "KEY_TAP", "key": selected_key, "delayMs": 20})
            elif act_type == "KEY_DOWN":
                actions.append({"type": "KEY_DOWN", "key": selected_key})
            elif act_type == "KEY_UP":
                actions.append({"type": "KEY_UP", "key": selected_key})

        elif act_type in ("MOUSE_CLICK", "MOUSE_DOWN", "MOUSE_UP"):
            btn_options = ["BTN_LEFT", "BTN_RIGHT", "BTN_MIDDLE", "BTN_SIDE", "BTN_EXTRA"]
            chosen, ok = QInputDialog.getItem(self, "Fare Tuşu Seç", "Makro fare tuşu:", btn_options, 0, False)
            btn_name = chosen if ok else "BTN_LEFT"
            if act_type == "MOUSE_CLICK":
                actions.append({"type": "MOUSE_CLICK", "mouseButton": btn_name, "delayMs": 15})
            elif act_type == "MOUSE_DOWN":
                actions.append({"type": "MOUSE_DOWN", "mouseButton": btn_name})
            elif act_type == "MOUSE_UP":
                actions.append({"type": "MOUSE_UP", "mouseButton": btn_name})

        elif act_type == "DELAY":
            ms, ok = QInputDialog.getInt(self, "Gecikme Süresi", "Milisaniye (ms):", 50, 1, 60000)
            if ok:
                actions.append({"type": "DELAY", "delayMs": ms, "jitterMs": 2})

        elif act_type == "TEXT":
            text, ok = QInputDialog.getText(self, "Metin Makrosu", "Yazdırılacak metni girin:")
            if ok and text:
                actions.append({"type": "TEXT", "text": text})
            elif ok:
                actions.append({"type": "TEXT", "text": "Selam CachyOS!"})

        self.refresh_editor_actions_table()
        if actions:
            self.action_table.selectRow(len(actions) - 1)

    def edit_selected_editor_action(self):
        r = self.action_table.currentRow()
        actions = getattr(self, "current_editing_actions", [])
        if not (0 <= r < len(actions)):
            return
        act = actions[r]
        act_type = act.get("type", "")

        if act_type in ("KEY_TAP", "KEY_DOWN", "KEY_UP"):
            dlg = KeyCaptureDialog(self)
            dlg.setWindowTitle("Yeni Tuşa Basın")
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.captured_key:
                act["key"] = dlg.captured_key.split("+")[-1]
            if act_type == "KEY_TAP":
                cur_del = act.get("delayMs", 20)
                ms, ok = QInputDialog.getInt(self, "Tuş Basma Süresi", "Tuş basılı kalma süresi (ms):", cur_del, 1, 10000)
                if ok:
                    act["delayMs"] = ms

        elif act_type in ("MOUSE_CLICK", "MOUSE_DOWN", "MOUSE_UP"):
            btn_options = ["BTN_LEFT", "BTN_RIGHT", "BTN_MIDDLE", "BTN_SIDE", "BTN_EXTRA"]
            cur_btn = act.get("mouseButton", "BTN_LEFT")
            cur_idx = btn_options.index(cur_btn) if cur_btn in btn_options else 0
            chosen, ok = QInputDialog.getItem(self, "Fare Tuşu Değiştir", "Fare tuşu:", btn_options, cur_idx, False)
            if ok:
                act["mouseButton"] = chosen

        elif act_type == "DELAY":
            cur_del = act.get("delayMs", 50)
            ms, ok = QInputDialog.getInt(self, "Gecikme Süresi", "Milisaniye (ms):", cur_del, 1, 60000)
            if ok:
                act["delayMs"] = ms

        elif act_type == "TEXT":
            cur_txt = act.get("text", "")
            text, ok = QInputDialog.getText(self, "Metin Düzenle", "Yazdırılacak metin:", text=cur_txt)
            if ok:
                act["text"] = text

        self.refresh_editor_actions_table()
        self.action_table.selectRow(r)

    def clear_all_editor_actions(self):
        actions = getattr(self, "current_editing_actions", [])
        if actions:
            reply = QMessageBox.question(
                self,
                "Tüm Eylemleri Sil",
                "Bu makrodaki tüm eylemleri silmek istediğinizden emin misiniz?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                actions.clear()
                self.refresh_editor_actions_table()

    def delete_editor_action(self):
        r = self.action_table.currentRow()
        actions = getattr(self, "current_editing_actions", [])
        if 0 <= r < len(actions):
            del actions[r]
            self.refresh_editor_actions_table()
        elif actions:
            del actions[-1]
            self.refresh_editor_actions_table()

    def save_macro_from_editor(self):
        macros = self.profile_data.get("macros", [])
        if 0 <= self.selected_macro_idx < len(macros):
            m = macros[self.selected_macro_idx]
            m["name"] = self.edit_name.text().strip() or "İsimsiz Makro"
            new_key = self.combo_trigger_key.currentText().strip()
            m["triggerKey"] = new_key
            mode_reverse = ["ONCE", "WHILE_HELD", "TOGGLE_LOOP", "REPEAT_COUNT", "DOUBLE_TAP", "HOLD_LONG_PRESS", "PRESS_AND_RELEASE"]
            c_idx = self.combo_mode.currentIndex()
            m["triggerMode"] = mode_reverse[c_idx] if 0 <= c_idx < len(mode_reverse) else "ONCE"
            m["repeatCount"] = self.spin_repeat.value()
            m["actions"] = getattr(self, "current_editing_actions", [])
            self.save_profile_to_disk(restart_daemon=True)
            self.refresh_macro_table()

            self.btn_save_macro.setText("Kaydedildi...")
            self.btn_save_macro.setEnabled(False)
            QTimer.singleShot(500, lambda: (
                self.btn_save_macro.setText("Kaydet"),
                self.btn_save_macro.setEnabled(True),
                self.tabs.setCurrentIndex(0)
            ))

    # SEKME 3: Canlı Kaydedici
    def setup_recorder_tab(self):
        layout = QVBoxLayout(self.tab_recorder)
        layout.addWidget(QLabel("Milisaniye hassasiyetinde canlı klavye ve fare hareketlerini kaydeder."))

        self.rec_table = QTableWidget()
        self.rec_table.setColumnCount(4)
        self.rec_table.setHorizontalHeaderLabels(["Sıra", "Olay", "Tuş / Buton", "Gecikme (ms)"])
        self.rec_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.rec_table)

        b_box = QHBoxLayout()
        self.btn_start_rec = QPushButton("⏺️ Kaydı Başlat")
        self.btn_start_rec.clicked.connect(self.toggle_recording)
        b_box.addWidget(self.btn_start_rec)

        btn_clear = QPushButton("🗑️ Temizle")
        btn_clear.clicked.connect(self.clear_recorded)
        b_box.addWidget(btn_clear)

        btn_conv = QPushButton("💾 Kaydı Yeni Makro Olarak Ekle")
        btn_conv.clicked.connect(self.convert_recording_to_macro)
        b_box.addWidget(btn_conv)

        layout.addLayout(b_box)

    def toggle_recording(self):
        self.recording_active = not self.recording_active
        if self.recording_active:
            # Kayıt esnasında makroların devreye girmemesi için motoru durdur
            if self.is_daemon_running():
                self.was_recording_daemon_running = True
                self.stop_daemon()
            else:
                self.was_recording_daemon_running = False

            self.btn_start_rec.setText("⏹️ Kaydı Durdur")
            self.btn_start_rec.setStyleSheet("background-color: #ef4444; color: white;")
            self.last_key_time = time.time()
            self.grabKeyboard()
            self.show_autosave_banner("🛑 Canlı kayıt modu: Diğer tüm makrolar durduruldu.")
        else:
            self.btn_start_rec.setText("⏺️ Kaydı Başlat")
            self.btn_start_rec.setStyleSheet("")
            self.releaseKeyboard()
            if getattr(self, "was_recording_daemon_running", False):
                self.restart_daemon(show_message=False)
                self.show_autosave_banner("▶ Makro motoru tekrar aktif edildi.")

    def mousePressEvent(self, event):
        if self.recording_active:
            m_btn = "LEFT" if event.button() == Qt.MouseButton.LeftButton else "RIGHT"
            now = time.time()
            delta = int((now - self.last_key_time) * 1000)
            self.last_key_time = now
            if delta > 10 and self.recorded_events:
                self.recorded_events.append({"type": "DELAY", "delayMs": delta, "jitterMs": 2})
            self.recorded_events.append({"type": "MOUSE_DOWN", "mouseButton": m_btn})
            self.refresh_rec_table()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        # STOP kontrolü
        k_seq = QKeySequence(event.key()).toString().upper()
        if k_seq == PANIC_KEY.replace("KEY_", "").upper() or event.key() == Qt.Key.Key_Pause:
            self.trigger_panic()
            return

        if event.key() == Qt.Key.Key_Escape and not self.recording_active:
            self.tabs.setCurrentIndex(0)
            return

        if self.recording_active:
            now = time.time()
            delta = int((now - self.last_key_time) * 1000)
            self.last_key_time = now
            key_code = f"KEY_{k_seq}" if k_seq else f"KEY_CODE_{event.key()}"
            if delta > 10 and self.recorded_events:
                self.recorded_events.append({"type": "DELAY", "delayMs": delta, "jitterMs": 2})
            self.recorded_events.append({"type": "KEY_DOWN", "key": key_code})
            self.refresh_rec_table()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if self.recording_active:
            now = time.time()
            delta = int((now - self.last_key_time) * 1000)
            self.last_key_time = now
            k_seq = QKeySequence(event.key()).toString().upper()
            key_code = f"KEY_{k_seq}" if k_seq else f"KEY_CODE_{event.key()}"
            if delta > 10 and self.recorded_events:
                self.recorded_events.append({"type": "DELAY", "delayMs": delta, "jitterMs": 2})
            self.recorded_events.append({"type": "KEY_UP", "key": key_code})
            self.refresh_rec_table()
            return
        super().keyReleaseEvent(event)

    def refresh_rec_table(self):
        self.rec_table.setRowCount(len(self.recorded_events))
        for i, ev in enumerate(self.recorded_events):
            self.rec_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.rec_table.setItem(i, 1, QTableWidgetItem(ev.get("type", "")))
            self.rec_table.setItem(i, 2, QTableWidgetItem(ev.get("key") or ev.get("mouseButton") or "-"))
            self.rec_table.setItem(i, 3, QTableWidgetItem(str(ev.get("delayMs", "-"))))

    def clear_recorded(self):
        self.recorded_events.clear()
        self.rec_table.setRowCount(0)

    def convert_recording_to_macro(self):
        if not self.recorded_events: return
        new_m = {
            "id": f"macro-{int(time.time() * 1000)}",
            "name": f"Kayıtlı Makro ({len(self.recorded_events)} adım)",
            "description": "Canlı kaydedici ile oluşturuldu",
            "enabled": True,
            "triggerKey": "KEY_LEFTSHIFT+KEY_LEFTCTRL",
            "triggerMode": "ONCE",
            "repeatCount": 1,
            "actions": list(self.recorded_events)
        }
        self.profile_data.setdefault("macros", []).append(new_m)
        self.save_profile_to_disk(restart_daemon=True)
        self.refresh_macro_table()
        self.tabs.setCurrentWidget(self.tab_macros)

    # SEKME 4: Sistem
    def setup_system_tab(self):
        layout = QVBoxLayout(self.tab_system)
        self.sys_info = QTextEdit()
        self.sys_info.setReadOnly(True)
        layout.addWidget(self.sys_info)

        p_box = QHBoxLayout()
        btn_fix = QPushButton("🛡️ Donanım İzinlerini Otomatik Düzelt (setfacl)")
        btn_fix.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold; padding: 8px;")
        btn_fix.clicked.connect(self.fix_permissions)
        p_box.addWidget(btn_fix)

        btn_ref = QPushButton("🔄 Durumu Yenile")
        btn_ref.clicked.connect(self.refresh_system_status)
        p_box.addWidget(btn_ref)

        layout.addLayout(p_box)
        self.refresh_system_status()

    def refresh_system_status(self):
        uinput_ok = os.access("/dev/uinput", os.W_OK)
        guide_text = f"""=== MacroStat Donanım ve Sistem Tanılama ===
Kernel /dev/uinput: {"✔ Erişilebilir (Yazma İzni Var)" if uinput_ok else "❌ Erişim Yok (İzin Gerekli)"}
Motor İkili Dosyası: {DAEMON_BIN or "İkili Dosya Bulunamadı (cargo build --release çalıştırın)"}
Profil Dosyası: {PROFILE_PATH.resolve() if PROFILE_PATH else "Bulunamadı"}
Acil Durdurma Tuşu (STOP): {PANIC_KEY}
Log Dosyası: {LOG_FILE}
"""
        self.sys_info.setPlainText(guide_text)

    def fix_permissions(self):
        try:
            import getpass
            username = os.environ.get("SUDO_USER") or os.environ.get("USER") or getpass.getuser()
            cmd = (
                f"pkexec sh -c 'modprobe uinput 2>/dev/null; "
                f"chmod 666 /dev/uinput 2>/dev/null; "
                f"chmod 666 /dev/input/event* 2>/dev/null; "
                f"setfacl -m u:{username}:rw /dev/uinput 2>/dev/null; "
                f"setfacl -m u:{username}:rw /dev/input/event* 2>/dev/null; "
                f"usermod -aG input {username} 2>/dev/null; "
                f"udevadm control --reload-rules 2>/dev/null; "
                f"udevadm trigger 2>/dev/null' 2>/dev/null || "
                f"sudo sh -c 'chmod 666 /dev/uinput /dev/input/event* 2>/dev/null; usermod -aG input {username} 2>/dev/null'"
            )
            subprocess.run(cmd, shell=True)
            time.sleep(0.2)
            self.restart_daemon(show_message=False)
            self.refresh_system_status()
            QMessageBox.information(self, "İzinler Düzeltildi", "Donanım izinleri başarıyla güncellendi ve motor başlatıldı.")
        except Exception as e:
            QMessageBox.critical(self, "Hata", str(e))

    def is_daemon_running(self):
        if self.daemon_proc is not None:
            if self.daemon_proc.poll() is None:
                return True
        try:
            res = subprocess.run(["pgrep", "-f", "cachymacro-daemon"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            return bool(res.stdout.strip())
        except Exception:
            return False

    def check_and_auto_start_daemon(self):
        if getattr(self, "is_manually_stopped", False) or getattr(self, "was_editor_daemon_running", False):
            return
        if not self.is_daemon_running():
            self.restart_daemon(show_message=False)

    def update_daemon_status(self):
        if getattr(self, "is_manually_stopped", False):
            self.lbl_stopped.show()
            self.status_badge.setText("🔴 Motor Durduruldu (STOP)")
            self.status_badge.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 13px;")
            return
        if getattr(self, "was_editor_daemon_running", False):
            self.status_badge.setText("🛑 Düzenleme Modu (Beklemede)")
            self.status_badge.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 13px;")
            return
        if self.is_daemon_running():
            self.failed_status_checks = 0
            self.status_badge.setText("🟢 Aktif")
            self.status_badge.setStyleSheet("color: #10b981; font-weight: bold; font-size: 13px;")
            self.btn_view_log.setText("📋 Günlük")
            if hasattr(self, 'btn_quick_fix'):
                self.btn_quick_fix.hide()
        else:
            self.failed_status_checks += 1
            if self.failed_status_checks >= 2:
                self.status_badge.setText("🔴 Motor Durduruldu")
                self.status_badge.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 13px;")
                self.btn_view_log.setText("⚠️ Hatayı İncele")
                if hasattr(self, 'btn_quick_fix'):
                    self.btn_quick_fix.show()

    def stop_daemon(self):
        global DAEMON_PROC
        try:
            if self.daemon_proc is not None:
                try:
                    if hasattr(os, "killpg"):
                        os.killpg(os.getpgid(self.daemon_proc.pid), signal.SIGKILL)
                    else:
                        self.daemon_proc.kill()
                except Exception:
                    pass
                self.daemon_proc = None
            DAEMON_PROC = None
            subprocess.run(["pkill", "-9", "-f", "cachymacro-daemon"], stderr=subprocess.DEVNULL)
            self.update_daemon_status()
        except Exception:
            pass

    def restart_daemon(self, show_message=False):
        global DAEMON_BIN, PROFILE_PATH, DAEMON_PROC
        self.is_manually_stopped = False
        self.lbl_stopped.hide()
        if hasattr(self, 'btn_restart_daemon'):
            self.btn_restart_daemon.setStyleSheet("")

        DAEMON_BIN, PROFILE_PATH = locate_paths()
        try:
            if self.daemon_proc is not None:
                try:
                    if hasattr(os, "killpg"):
                        os.killpg(os.getpgid(self.daemon_proc.pid), signal.SIGTERM)
                    else:
                        self.daemon_proc.terminate()
                    self.daemon_proc.wait(timeout=0.2)
                except Exception:
                    try:
                        self.daemon_proc.kill()
                    except Exception:
                        pass
                self.daemon_proc = None

            subprocess.run(["pkill", "-9", "-f", "cachymacro-daemon"], stderr=subprocess.DEVNULL)
            time.sleep(0.08)

            if not DAEMON_BIN or not DAEMON_BIN.exists():
                cargo_candidates = [
                    SCRIPT_DIR / "Cargo.toml",
                    SCRIPT_DIR / "cachymacro" / "Cargo.toml",
                    SCRIPT_DIR.parent / "Cargo.toml",
                    SCRIPT_DIR.parent / "cachymacro" / "Cargo.toml",
                ]
                cargo_dir = None
                for c in cargo_candidates:
                    if c.exists() and c.is_file():
                        cargo_dir = c.parent
                        break

                if cargo_dir and shutil.which("cargo"):
                    self.status_badge.setText("⚙️ Motor derleniyor...")
                    self.status_badge.setStyleSheet("color: #38bdf8; font-weight: bold;")
                    QApplication.processEvents()
                    try:
                        subprocess.run(["cargo", "build", "--release"], cwd=cargo_dir, check=False)
                        DAEMON_BIN, PROFILE_PATH = locate_paths()
                    except Exception:
                        pass

            if not DAEMON_BIN or not DAEMON_BIN.exists():
                if show_message:
                    QMessageBox.warning(self, "Motor Bulunamadı", "Lütfen terminalde 'cargo build --release' komutunu çalıştırın.")
                self.update_daemon_status()
                return

            log_f = open(LOG_FILE, "a", encoding="utf-8")
            self.daemon_proc = subprocess.Popen(
                [str(DAEMON_BIN.resolve()), str(PROFILE_PATH.resolve())],
                cwd=str(DAEMON_BIN.parent.parent if DAEMON_BIN.parent.name == "release" else DAEMON_BIN.parent),
                stdout=log_f,
                stderr=subprocess.STDOUT,
                start_new_session=True
            )
            DAEMON_PROC = self.daemon_proc

            if show_message:
                time.sleep(0.3)
                self.failed_status_checks = 0
                self.update_daemon_status()
                QMessageBox.information(self, "Başarılı", "Makro motoru başlatıldı.")
            else:
                QTimer.singleShot(350, self.update_daemon_status)
        except Exception as e:
            if show_message:
                QMessageBox.critical(self, "Hata", str(e))

    def trigger_panic(self):
        try:
            self.is_manually_stopped = True
            self.lbl_stopped.show()
            self.stop_daemon()
            self.status_badge.setText("🔴 Motor Durduruldu (STOP)")
            self.status_badge.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 13px;")
            self.btn_restart_daemon.setStyleSheet("background-color: #10b981; color: #022c22; font-weight: bold; border-radius: 6px; padding: 6px 14px;")
            self.show_autosave_banner("🛑 STOP Tetiklendi! Motor 'Yeniden Başlat' butonuna basılana dek kapalı kalacaktır.")
        except Exception:
            pass

    def show_daemon_log(self):
        content = "Log dosyası henüz oluşmadı."
        if LOG_FILE.exists():
            try:
                with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception as e:
                content = f"Log okunamadı: {e}"
        dlg = QDialog(self)
        dlg.setWindowTitle("Motor Günlüğü")
        dlg.resize(600, 400)
        l = QVBoxLayout(dlg)
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setPlainText(content)
        l.addWidget(txt)
        dlg.exec()

    def closeEvent(self, event):
        try:
            self.status_timer.stop()
        except Exception:
            pass
        cleanup_daemon()
        event.accept()

def main():
    app = QApplication(sys.argv)
    app.aboutToQuit.connect(cleanup_daemon)
    window = MacroStatApp()
    window.show()
    exit_code = app.exec()
    cleanup_daemon()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()

EOF

# Ana klasör için de kopyaları hazırla
cp cachymacro/profile.json ./profile.json 2>/dev/null || true
cp cachymacro/gui.py ./gui.py 2>/dev/null || true
cp cachymacro/KULLANIM_KILAVUZU.md ./KULLANIM_KILAVUZU.md 2>/dev/null || true

cat << 'EOF' > cachymacro/baslat-arayuz.sh
#!/bin/bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"
trap "pkill -9 -f cachymacro-daemon 2>/dev/null || true" EXIT INT TERM
python3 gui.py
pkill -9 -f cachymacro-daemon 2>/dev/null || true
EOF
chmod +x cachymacro/baslat-arayuz.sh

cat << 'EOF' > ./baslat-arayuz.sh
#!/bin/bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
if [ -f "$DIR/cachymacro/gui.py" ]; then
    cd "$DIR/cachymacro"
else
    cd "$DIR"
fi
trap "pkill -9 -f cachymacro-daemon 2>/dev/null || true" EXIT INT TERM
python3 gui.py
pkill -9 -f cachymacro-daemon 2>/dev/null || true
EOF
chmod +x ./baslat-arayuz.sh

echo "🛡️ [3/6] udev donanım izin kuralı tanımlanıyor..."
sudo tee /etc/udev/rules.d/99-cachymacro.rules > /dev/null << 'EOF'
KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", OPTIONS+="static_node=uinput", GROUP="input", MODE="0666"
SUBSYSTEM=="input", KERNEL=="event*", TAG+="uaccess", GROUP="input", MODE="0666"
EOF

sudo modprobe uinput || true
sudo udevadm control --reload-rules && sudo udevadm trigger || true
sudo usermod -aG input "$USER" || true
sudo chmod 666 /dev/uinput /dev/input/event* 2>/dev/null || true
sudo setfacl -m u:"$USER":rw /dev/uinput /dev/input/event* 2>/dev/null || true

echo "⚙️ [4/6] Rust makro motoru derleniyor (Release modunda)..."
cd cachymacro
cargo build --release
cp target/release/cachymacro-daemon ../cachymacro-daemon 2>/dev/null || true
cp target/release/cachymacro-daemon ./cachymacro-daemon 2>/dev/null || true
chmod +x ./cachymacro-daemon ../cachymacro-daemon 2>/dev/null || true

echo "✅ [5/6] Kurulum tamamlandı!"
echo "Şimdi arayüzü başlatmak için:"
echo "./baslat-arayuz.sh"
