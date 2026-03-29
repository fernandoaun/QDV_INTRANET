from __future__ import annotations

import logging
import tkinter as tk

from qdv_salmuera.config.settings import project_root
from qdv_salmuera.data.db import DB
from qdv_salmuera.ui.login_window import LoginWindow
from qdv_salmuera.ui.mainapp import QDVApp
from qdv_salmuera.utils.app_paths import (
    get_database_path,
    migrate_legacy_database_if_needed,
    setup_persistent_logging,
)


def main() -> None:
    setup_persistent_logging(prefer_roaming=True)
    mig = migrate_legacy_database_if_needed(project_root=project_root(), prefer_roaming=True)
    if mig:
        logging.info(mig)

    db_path = get_database_path(prefer_roaming=True)
    logging.info("Usando base de datos en: %s", db_path)
    db = DB(db_path)

    while True:
        login_root = tk.Tk()
        holder: dict = {"session": None}

        def on_success(sess):
            holder["session"] = sess

        LoginWindow(login_root, db, on_success)
        login_root.mainloop()
        try:
            login_root.destroy()
        except Exception:
            pass

        sess = holder["session"]
        if sess is None:
            break

        app = QDVApp(session=sess, db=db)
        app.mainloop()

        if not getattr(app, "_logout_requested", False):
            break


if __name__ == "__main__":
    main()
