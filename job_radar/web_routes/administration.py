"""Serve the session-scoped Administration access boundary."""

from flask import (
    Flask,
    redirect,
    render_template,
    request,
    url_for,
)

from job_radar.admin_access import (
    administration_required,
    is_admin_unlocked,
    lock_admin_session,
    safe_local_path,
    unlock_admin_session,
)


def register_administration_routes(app: Flask) -> None:
    """Register Administration shell routes without global edit controls."""

    @app.context_processor
    def administration_context() -> dict[str, bool]:
        return {"admin_mode_active": is_admin_unlocked()}

    @app.get("/administration")
    @administration_required
    def administration() -> str:
        return render_template("administration/index.html")

    @app.get("/administration/unlock")
    def administration_unlock() -> str:
        next_path = safe_local_path(request.args.get("next"))
        if is_admin_unlocked():
            return redirect(next_path or url_for("administration"))

        return render_template(
            "administration/unlock.html",
            next_path=next_path or "",
            unlock_error=request.args.get("error") == "invalid",
        )

    @app.post("/administration/unlock")
    def administration_unlock_submit():
        next_path = safe_local_path(request.form.get("next"))
        if request.form.get("confirmation", "").strip() != "ADMIN":
            return redirect(
                url_for(
                    "administration_unlock",
                    next=next_path,
                    error="invalid",
                )
            )

        unlock_admin_session()
        return redirect(next_path or url_for("administration"))

    @app.post("/administration/lock")
    def administration_lock():
        lock_admin_session()
        return redirect(safe_local_path(request.form.get("next")) or url_for("index"))
