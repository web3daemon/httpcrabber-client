"""Браузер сессии в терминале: `httpcrabber browse [SESSION]`.

Слева — все запросы с фильтром, справа — запрос, ответ, кадры WebSocket, curl и
повтор. Повтор отправляет запрос заново (как есть или после правки) и показывает
ответ рядом с записанным.
"""

import copy
import json
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from rich.console import Group, RenderableType
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)

from httpcrabber import export, ui
from httpcrabber.config import CYAN, DIM, ERR, MAG, NEON, WARN
from httpcrabber.dump import Exchange, body_text, is_truncated, load
from httpcrabber.replay import ReplayResult, replay

THEME = Theme(
    name="httpcrabber",
    primary="#39ff14",
    secondary="#00e5ff",
    accent="#ff2fd0",
    warning="#ffcc00",
    error="#ff3b3b",
    success="#39ff14",
    foreground="#d6ded6",
    background="#0b0f0c",
    surface="#111812",
    panel="#172019",
    dark=True,
)

# ── фильтр ───────────────────────────────────────────────────────────────────

def matches(ex: Exchange, query: str) -> bool:
    """`method:POST status:4xx host:api graphql` — все условия через И."""
    for token in query.split():
        key, sep, value = token.partition(":")
        key, value = key.lower(), value.lower()
        if sep and key == "method":
            if ex.method.lower() != value:
                return False
        elif sep and key == "status":
            code = str(ex.status or "")
            if not (code == value or (len(value) == 3 and value.endswith("xx")
                                      and code[:1] == value[0])):
                return False
        elif sep and key == "host":
            if value not in ex.host.lower():
                return False
        elif token.lower() not in ex.url.lower():
            return False
    return True


# ── отрисовка деталей ────────────────────────────────────────────────────────

def _mime(value: str | None) -> str:
    return (value or "").split(";")[0].strip().lower()


def _headers_table(pairs) -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style=CYAN, no_wrap=True)
    table.add_column(overflow="fold")
    for name, value in pairs:
        table.add_row(name, value)
    return table


def render_body(body: object, mime: str) -> RenderableType:
    if body is None or body == "":
        return Text("no body", style=DIM)
    if isinstance(body, dict) and body.get("encoding") == "base64":
        return Text(f"binary, {body.get('bytes')} bytes (base64 in the dump)", style=DIM)
    text = body_text(body)
    if text is None:
        return Text(str(body), style=DIM)
    note = Text("\n…truncated in the dump (HTTPCRABBER_MAX_BODY)", style=WARN) \
        if is_truncated(text) else None
    text = text.removesuffix("...[TRUNCATED]")
    lexer = None
    if "json" in mime or text.lstrip()[:1] in "{[":
        try:
            text, lexer = json.dumps(json.loads(text), indent=2, ensure_ascii=False), "json"
        except ValueError:
            lexer = "json" if "json" in mime else None
    elif "x-www-form-urlencoded" in mime:
        return Group(_headers_table(parse_qsl(text, keep_blank_values=True)), *([note] if note else []))
    elif "html" in mime or "xml" in mime:
        lexer = "html" if "html" in mime else "xml"
    elif "javascript" in mime:
        lexer = "javascript"
    if len(text) > 200_000:
        text = text[:200_000] + "\n…"
    content = Syntax(text, lexer, theme="monokai", word_wrap=True, background_color="default") \
        if lexer else Text(text)
    return Group(content, *([note] if note else []))


def _section(title: str) -> Text:
    return Text(f"\n{title}", style=f"bold {MAG}")


def render_request(ex: Exchange) -> RenderableType:
    head = Text.assemble((ex.method, ui._METHOD_STYLE.get(ex.method, "bold white")), " ",
                         (ex.url, "bold white"), (f"  {ex.http_version}", DIM))
    query = parse_qsl(urlsplit(ex.url).query, keep_blank_values=True)
    parts = [head]
    if ex.fetched_by:
        parts.append(Text(f"fetched by httpcrabber ({ex.fetched_by})", style=DIM))
    if query:
        parts += [_section("Query"), _headers_table(query)]
    parts += [_section("Headers"), _headers_table(ex.req_headers),
              _section("Body"), render_body(ex.req_body, _mime(ex.header("content-type")))]
    return Group(*parts)


def _url_cell(host: str, path: str, width: int = 40) -> Text:
    """Хост ярко, путь тише; длинное режем с конца пути, а не хоста."""
    host = host if len(host) <= 24 else "…" + host[-23:]
    room = max(8, width - len(host))
    path = path if len(path) <= room else path[: room - 1] + "…"
    return Text.assemble((host, "bold"), (path, "#9aa89a"))


def _status_text(status, reason: str = "") -> Text:
    return Text(f"{status or '···'} {reason}".strip(), style=ui.status_style(status))


def render_response(ex: Exchange) -> RenderableType:
    if ex.status is None:
        return Text(ex.error or "no response recorded", style=ERR)
    meta = Text.assemble(_status_text(ex.status, ex.reason),
                         (f"   {ex.duration_ms} ms" if ex.duration_ms is not None else "", DIM),
                         (f"   {ui.fmt_size(ex.resp_size)}" if ex.resp_size else "", DIM))
    return Group(meta, _section("Headers"), _headers_table(ex.resp_headers), _section("Body"),
                 render_body(ex.resp_body, _mime(ex.header("content-type", "resp"))))


def render_ws(ex: Exchange) -> RenderableType:
    if not ex.ws:
        return Text("no WebSocket frames", style=DIM)
    table = Table.grid(padding=(0, 2))
    table.add_column(style=DIM, no_wrap=True)
    table.add_column(no_wrap=True)
    table.add_column(overflow="fold")
    for m in ex.ws:
        arrow = Text("→ out", style=CYAN) if m.get("from_client") else Text("← in", style=NEON)
        content = m.get("content")
        shown = content if isinstance(content, str) else f"binary ({content.get('bytes')} bytes)"
        table.add_row(str(m.get("ts", ""))[11:23], arrow, shown)
    return table


def render_replay(ex: Exchange, result: ReplayResult | None) -> RenderableType:
    if result is None:
        return Text("press r to send this request again, e to edit it first", style=DIM)
    if result.error:
        return Text(result.error, style=ERR)
    same = ex.status == result.status
    verdict = Text("same status as recorded" if same else f"recorded: {ex.status}",
                   style=NEON if same else WARN)
    mime = _mime(next((v for k, v in result.headers if k.lower() == "content-type"), ""))
    return Group(
        Text.assemble(_status_text(result.status, result.reason), (f"   {result.duration_ms} ms   ", DIM),
                      verdict),
        _section("Headers"), _headers_table(result.headers),
        _section("Body"), render_body(result.body, mime),
    )


# ── правка перед повтором ───────────────────────────────────────────────────

class EditScreen(ModalScreen[Exchange | None]):
    DEFAULT_CSS = """
    EditScreen { align: center middle; }
    #edit { width: 90%; height: 90%; border: round $accent; background: $surface; padding: 1 2; }
    #edit TextArea { height: 1fr; }
    #edit #buttons { height: 3; align-horizontal: right; }
    #edit Label { color: $secondary; margin-top: 1; }
    """
    BINDINGS = [Binding("escape", "cancel", "Cancel"), Binding("ctrl+s", "send", "Send")]

    def __init__(self, ex: Exchange):
        super().__init__()
        self.ex = ex

    def compose(self) -> ComposeResult:
        body = self.ex.req_body if isinstance(self.ex.req_body, str) else ""
        with Vertical(id="edit"):
            with Horizontal(id="line"):
                yield Input(self.ex.method, id="method", classes="method")
                yield Input(self.ex.url, id="url")
            yield Label("Headers — one per line, Name: value")
            yield TextArea("\n".join(f"{k}: {v}" for k, v in self.ex.req_headers
                                     if not k.startswith(":")), id="headers")
            yield Label("Body")
            yield TextArea(body.removesuffix("...[TRUNCATED]"), id="body")
            with Horizontal(id="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Send  ctrl+s", id="send", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#method", Input).styles.width = 12

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_send(self) -> None:
        ex = copy.copy(self.ex)
        ex.method = self.query_one("#method", Input).value.strip().upper() or "GET"
        ex.url = self.query_one("#url", Input).value.strip()
        ex.req_headers = [(k.strip(), v.strip()) for line in
                          self.query_one("#headers", TextArea).text.splitlines()
                          if ":" in line for k, v in [line.split(":", 1)] if k.strip()]
        ex.req_body = self.query_one("#body", TextArea).text or None
        self.dismiss(ex)

    @on(Button.Pressed, "#send")
    def _send(self) -> None:
        self.action_send()

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.action_cancel()


# ── приложение ───────────────────────────────────────────────────────────────

class BrowseApp(App):
    TITLE = "httpcrabber"
    CSS = """
    #filter { margin: 0 1; border: round $panel-lighten-2; }
    #filter:focus { border: round $accent; }
    #main { height: 1fr; }
    #list { width: 60%; height: 100%; border: round $panel-lighten-2; }
    #list:focus { border: round $primary; }
    #list > .datatable--cursor { background: $primary 25%; color: $foreground; text-style: bold; }
    #list > .datatable--header { color: $secondary; background: $surface; }
    #tabs { width: 40%; height: 100%; }
    VerticalScroll { padding: 0 1; }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("slash", "focus_filter", "Filter"),
        Binding("escape", "clear_filter", "Clear", show=False),
        Binding("r", "replay", "Replay"),
        Binding("e", "edit", "Edit & replay"),
        Binding("c", "copy_curl", "Copy curl"),
        Binding("1", "tab('t-req')", "Request", show=False),
        Binding("2", "tab('t-resp')", "Response", show=False),
        Binding("3", "tab('t-ws')", "WS", show=False),
        Binding("4", "tab('t-curl')", "curl", show=False),
        Binding("5", "tab('t-replay')", "Replay", show=False),
    ]

    def __init__(self, session: Path, proxy: str | None = None, shell: str = "posix"):
        super().__init__()
        self.session, self.proxy, self.shell = session, proxy, shell
        self.label = session.name if session.is_dir() else session.stem
        self.exchanges = load(session)
        self.by_id = {ex.id: ex for ex in self.exchanges}
        self.shown: list[Exchange] = []
        self.current: Exchange | None = None
        self.replays: dict[str, ReplayResult] = {}
        self.ready = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Input(placeholder="filter — text in URL, method:POST, status:4xx, host:api",
                    id="filter")
        with Horizontal(id="main"):
            table = DataTable(id="list", cursor_type="row", zebra_stripes=True)
            yield table
            with TabbedContent(id="tabs"):
                for tab_id, title, body_id in (("t-req", "Request", "req"),
                                               ("t-resp", "Response", "resp"),
                                               ("t-ws", "WebSocket", "ws"),
                                               ("t-curl", "curl", "curl"),
                                               ("t-replay", "Replay", "replay")):
                    with TabPane(title, id=tab_id):
                        yield VerticalScroll(Static(id=body_id))
        yield Footer()

    def on_mount(self) -> None:
        self.register_theme(THEME)
        self.theme = "httpcrabber"
        table = self.query_one(DataTable)
        table.add_columns("Time", "Method", "Status", "URL", "Size", "ms")
        self.refill()
        table.focus()
        self.ready = True

    def refill(self, query: str = "") -> None:
        table = self.query_one(DataTable)
        table.clear()
        # Колонке URL — всё, что остаётся после остальных (≈46 символов с отступами)
        url_width = max(24, int(self.size.width * 0.6) - 48)
        self.shown = [ex for ex in self.exchanges if matches(ex, query)]
        for ex in self.shown:
            parts = urlsplit(ex.url)
            path = parts.path + (f"?{parts.query}" if parts.query else "")
            table.add_row(
                Text(ex.started[11:19], style=DIM),
                Text(ex.method + (" ⇄" if ex.ws else ""), style=ui._METHOD_STYLE.get(ex.method, "")),
                _status_text(ex.status),
                _url_cell(ex.host, path, url_width),
                Text(ui.fmt_size(ex.resp_size) if ex.resp_size else "", style=DIM, justify="right"),
                Text(f"{ex.duration_ms:.0f}" if ex.duration_ms is not None else "", style=DIM,
                     justify="right"),
                key=ex.id,
            )
        shown = f"{len(self.shown)}/" if query else ""
        self.sub_title = f"{self.label} · {shown}{len(self.exchanges)} requests"
        if self.shown:
            self.show(self.shown[0])
        else:
            self.current = None
            for body_id in ("req", "resp", "ws", "curl", "replay"):
                self.query_one(f"#{body_id}", Static).update(Text("nothing matches", style=DIM))

    def on_resize(self) -> None:
        if self.ready:  # до on_mount у таблицы ещё нет колонок
            self.refill(self.query_one("#filter", Input).value)

    def show(self, ex: Exchange) -> None:
        self.current = ex
        self.query_one("#req", Static).update(render_request(ex))
        self.query_one("#resp", Static).update(render_response(ex))
        self.query_one("#ws", Static).update(render_ws(ex))
        self.query_one("#curl", Static).update(
            Syntax(export.to_curl(ex, self.shell), "bash", theme="monokai", word_wrap=True,
                   background_color="default"))
        self.query_one("#replay", Static).update(render_replay(ex, self.replays.get(ex.id)))

    @on(DataTable.RowHighlighted)
    def _highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key and event.row_key.value in self.by_id:
            self.show(self.by_id[event.row_key.value])

    @on(Input.Changed, "#filter")
    def _filter(self, event: Input.Changed) -> None:
        self.refill(event.value)

    @on(Input.Submitted, "#filter")
    def _filter_done(self) -> None:
        self.query_one(DataTable).focus()

    def action_focus_filter(self) -> None:
        self.query_one("#filter", Input).focus()

    def action_clear_filter(self) -> None:
        box = self.query_one("#filter", Input)
        if box.value:
            box.value = ""
        self.query_one(DataTable).focus()

    def action_tab(self, tab: str) -> None:
        self.query_one(TabbedContent).active = tab

    def action_copy_curl(self) -> None:
        if self.current:
            self.copy_to_clipboard(export.to_curl(self.current, self.shell))
            self.notify("curl command copied to the clipboard")

    def action_replay(self) -> None:
        if self.current:
            self.send(self.current, self.current.id)

    def action_edit(self) -> None:
        if not self.current:
            return
        original = self.current

        def done(edited: Exchange | None) -> None:
            if edited is not None:
                self.send(edited, original.id)

        self.push_screen(EditScreen(original), done)

    @work(thread=True, exclusive=True, group="replay")
    def send(self, ex: Exchange, key: str) -> None:
        self.call_from_thread(self.notify, f"{ex.method} {ex.url[:70]} …")
        result = replay(ex, self.proxy)
        self.call_from_thread(self._replayed, key, ex, result)

    def _replayed(self, key: str, ex: Exchange, result: ReplayResult) -> None:
        self.replays[key] = result
        original = self.by_id.get(key, ex)
        if self.current is original:
            self.query_one("#replay", Static).update(render_replay(original, result))
        self.action_tab("t-replay")
        if result.error:
            self.notify(result.error, severity="error")
        else:
            self.notify(f"{result.status} in {result.duration_ms} ms")
