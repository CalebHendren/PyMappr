//! Dev-only HTTP front door to the app's commands, for driving the UI from a
//! browser (`npm run dev` plus this). POST /core with {"cmd", "args"}.
//!
//!     cargo run -p rustymappr --bin devbridge --features devbridge

use std::sync::Arc;

use rustymappr_lib::core::Core;
use serde_json::{Value, json};
use tiny_http::{Header, Method, Response, Server};

const ADDR: &str = "127.0.0.1:1430";

fn main() {
    let core = Core::new();
    let server = Server::http(ADDR).expect("bind the dev bridge port");
    println!("RustyMappr dev bridge on http://{ADDR}");
    for mut request in server.incoming_requests() {
        let cors = [
            Header::from_bytes("Access-Control-Allow-Origin", "*").unwrap(),
            Header::from_bytes("Access-Control-Allow-Headers", "content-type").unwrap(),
            Header::from_bytes("Content-Type", "application/json").unwrap(),
        ];
        if request.method() == &Method::Options {
            let mut response = Response::empty(204);
            for h in cors {
                response.add_header(h);
            }
            let _ = request.respond(response);
            continue;
        }
        let mut body = String::new();
        let _ = request.as_reader().read_to_string(&mut body);
        let core = Arc::clone(&core);
        // One thread per request so a slow render does not block the rest.
        std::thread::spawn(move || {
            let reply = match serde_json::from_str::<Value>(&body) {
                Ok(v) => {
                    let cmd = v["cmd"].as_str().unwrap_or_default().to_string();
                    match core.dispatch(&cmd, v["args"].clone()) {
                        Ok(value) => json!({ "ok": value }),
                        Err(e) => json!({ "err": e }),
                    }
                }
                Err(e) => json!({ "err": format!("bad request: {e}") }),
            };
            let mut response = Response::from_string(reply.to_string());
            for h in cors {
                response.add_header(h);
            }
            let _ = request.respond(response);
        });
    }
}
