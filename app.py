import os
import json
import uvicorn

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import select
from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import settings, THEMES
from database import get_session, create_db_and_tables
from models import Movement, Event, MovementEventLink, ThemeSnapshot, TextSnapshot
from engine.themes import aggregate_themes

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

templates = Environment(
    loader=FileSystemLoader(os.path.join(BASE_DIR, "ui", "templates")),
    autoescape=select_autoescape(["html", "xml"]),
)

app = FastAPI(title=settings.app_name)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "ui", "static")), name="static")


def render(template_name: str, **ctx):
    tpl = templates.get_template(template_name)
    return HTMLResponse(tpl.render(**ctx))


@app.on_event("startup")
def startup():
    create_db_and_tables()


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    with get_session() as session:
        movements = session.exec(select(Movement)).all()
        m_dicts = [
            {
                "id": m.id,
                "theme": m.theme,
                "stabilized_impact": m.stabilized_impact,
                "confidence_score": m.confidence_score,
                "confidence_label": m.confidence_label,
                "acceleration_arrow": m.acceleration_arrow,
            }
            for m in movements
        ]
        themes = aggregate_themes(m_dicts) if m_dicts else []

        text = session.exec(select(TextSnapshot).order_by(TextSnapshot.created_at.desc())).first()

    top5 = themes[:5]
    bubble_data = [
        {
            "theme": t["theme"],
            "score": t["theme_score"],
            "arrow": t["acceleration_arrow"],
            "confidence": t["confidence_label"],
        }
        for t in top5
    ]

    executive_summary = text.executive_summary if text else "No snapshot yet. Run: python cli.py snapshot"
    discussion_topics = text.discussion_topics if text else ""

    return render(
        "dashboard.html",
        request=request,
        app_name=settings.app_name,
        themes=themes,
        top5=top5,
        bubble_data_json=json.dumps(bubble_data),
        executive_summary=executive_summary,
        discussion_topics=discussion_topics,
    )


@app.get("/theme/{theme_name}", response_class=HTMLResponse)
def theme_detail(request: Request, theme_name: str):
    with get_session() as session:
        movements = session.exec(
            select(Movement)
            .where(Movement.theme == theme_name)
            .order_by(Movement.stabilized_impact.desc())
        ).all()

    return render(
        "theme.html",
        request=request,
        app_name=settings.app_name,
        theme=theme_name,
        movements=movements,
    )


@app.get("/movement/{movement_id}", response_class=HTMLResponse)
def movement_detail(request: Request, movement_id: int):
    with get_session() as session:
        m = session.get(Movement, movement_id)
        links = session.exec(select(MovementEventLink).where(MovementEventLink.movement_id == movement_id)).all()
        ev_ids = [l.event_id for l in links]
        events = session.exec(select(Event).where(Event.id.in_(ev_ids)).order_by(Event.date.desc())).all()

    audit = {}
    try:
        audit = json.loads(m.audit_json or "{}") if m else {}
    except Exception:
        audit = {}

    return render(
        "movement.html",
        request=request,
        app_name=settings.app_name,
        movement=m,
        events=events,
        audit=audit,
    )


@app.get("/history", response_class=HTMLResponse)
def history(request: Request):
    with get_session() as session:
        theme_snaps = session.exec(select(ThemeSnapshot).order_by(ThemeSnapshot.created_at)).all()

    quarters = sorted({s.quarter_id for s in theme_snaps})
    series = {}
    for t in THEMES:
        pts = []
        for q in quarters:
            match = next((s for s in theme_snaps if s.theme == t and s.quarter_id == q), None)
            pts.append(match.theme_score if match else 0)
        series[t] = pts

    return render(
        "history.html",
        request=request,
        app_name=settings.app_name,
        quarters=quarters,
        series_json=json.dumps(series),
        themes=THEMES,
    )



@app.get("/frontier", response_class=HTMLResponse)
def frontier_page(request: Request):
    return render(
        "frontier.html",
        request=request,
        app_name=settings.app_name,
    )

def run_server(host: str = "127.0.0.1", port: int = 8000):
    uvicorn.run("app:app", host=host, port=port, reload=False)

@app.get("/api/frontier/themes")
def frontier_themes(top_n: int = 6, events_per_theme: int = 5):
    """
    Frontier Theme Briefs (board-grade)
    """
    from engine.api_frontier import get_frontier_theme_briefs
    return get_frontier_theme_briefs(top_n=top_n, events_per_theme=events_per_theme)

