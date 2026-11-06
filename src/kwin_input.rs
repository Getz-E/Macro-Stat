// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 MacroStat contributors
//
// KDE Wayland'da gerçek imleci mutlak bir ekran konumuna taşır.
//
// Wayland'da normal uygulamalar imleci keyfî bir noktaya taşıyamaz. KWin,
// KDE'ye özel `org_kde_kwin_fake_input` arayüzünü oturumda sunar ve bu arayüz
// mutlak konumlandırmayı destekler. Arayüz özel/kararsız bir uygulama detayıdır
// (protokol dokümanı normal uygulamaların kullanmamasını söyler); bu yüzden
// yalnızca özellik algılama ile, sessizce ve isteğe bağlı olarak kullanılır.
// Kullanılamıyorsa `false` döner ve oynatma mevcut davranışını korur.

#[allow(dead_code, non_camel_case_types, unused_imports)]
mod protocol {
    #[allow(clippy::single_component_path_imports)]
    use wayland_client;
    use wayland_client::backend as wayland_backend;
    use wayland_client::protocol::*;

    mod __interfaces {
        use wayland_client::backend as wayland_backend;
        use wayland_client::protocol::__interfaces::*;
        wayland_scanner::generate_interfaces!("protocols/fake-input.xml");
    }
    use self::__interfaces::*;

    wayland_scanner::generate_client_code!("protocols/fake-input.xml");
}

use wayland_client::globals::{registry_queue_init, GlobalListContents};
use wayland_client::protocol::wl_registry;
use wayland_client::{Connection, Dispatch, Proxy, QueueHandle};

struct State;

impl Dispatch<wl_registry::WlRegistry, GlobalListContents> for State {
    fn event(
        _: &mut Self,
        _: &wl_registry::WlRegistry,
        _: wl_registry::Event,
        _: &GlobalListContents,
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
    }
}

impl Dispatch<protocol::org_kde_kwin_fake_input::OrgKdeKwinFakeInput, ()> for State {
    fn event(
        _: &mut Self,
        _: &protocol::org_kde_kwin_fake_input::OrgKdeKwinFakeInput,
        _: <protocol::org_kde_kwin_fake_input::OrgKdeKwinFakeInput as Proxy>::Event,
        _: &(),
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
    }
}

/// İmleci KWin'in mantıksal ekran koordinatına taşır. Yalnızca KDE Wayland
/// oturumunda ve arayüz mevcutsa çalışır.
pub fn move_pointer_absolute(x: i32, y: i32) -> bool {
    if std::env::var_os("WAYLAND_DISPLAY").is_none() {
        return false;
    }
    let Ok(connection) = Connection::connect_to_env() else {
        return false;
    };
    let Ok((globals, mut queue)) = registry_queue_init::<State>(&connection) else {
        return false;
    };
    let handle = queue.handle();
    let Ok(fake) = globals.bind::<protocol::org_kde_kwin_fake_input::OrgKdeKwinFakeInput, _, _>(
        &handle,
        3..=6,
        (),
    ) else {
        return false;
    };
    let mut state = State;
    fake.authenticate(
        String::from("MacroStat"),
        String::from("Fare yolu başlangıç noktasına hizalama"),
    );
    fake.pointer_motion_absolute(f64::from(x), f64::from(y));
    // İsteğin sunucu tarafından işlenmesini bekle; ardından göreli yol
    // güvenli biçimde bu konumdan oynatılabilir.
    queue.roundtrip(&mut state).is_ok()
}
