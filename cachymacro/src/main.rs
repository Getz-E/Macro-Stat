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

