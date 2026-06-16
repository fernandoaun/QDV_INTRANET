(function () {
  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }
  function qsa(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }
  function escapeHtml(text) {
    var d = document.createElement("div");
    d.textContent = text || "";
    return d.innerHTML;
  }
  function formatTime(iso) {
    if (!iso) return "";
    try {
      var d = new Date(iso);
      if (isNaN(d.getTime())) return "";
      return d.toLocaleString("es-AR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
    } catch (e) {
      return "";
    }
  }
  function csrfHeaders(menu) {
    var token = menu.getAttribute("data-csrf-token") || "";
    var headers = { "Content-Type": "application/json", Accept: "application/json" };
    if (token) headers["X-CSRFToken"] = token;
    return headers;
  }
  function jsonFetch(url, options, menu) {
    options = options || {};
    options.credentials = "same-origin";
    options.headers = Object.assign({}, csrfHeaders(menu), options.headers || {});
    return fetch(url, options).then(function (resp) {
      return resp.json().catch(function () { return {}; }).then(function (data) {
        if (!resp.ok) {
          var err = new Error((data && data.message) || "Error de red");
          err.payload = data;
          err.status = resp.status;
          throw err;
        }
        return data;
      });
    });
  }

  function initInternalChat() {
    var menu = qs(".app-chat-menu");
    var btn = document.getElementById("appChatBtn");
    if (!menu || !btn || typeof bootstrap === "undefined" || !bootstrap.Dropdown) return;

    var state = {
      view: "list",
      threads: [],
      recipientsLoaded: false,
      activeThreadId: null,
      activeThread: null,
    };

    var listView = document.getElementById("appChatListView");
    var threadView = document.getElementById("appChatThreadView");
    var composeView = document.getElementById("appChatComposeView");
    var threadList = document.getElementById("appChatThreadList");
    var messagesEl = document.getElementById("appChatMessages");
    var headerTitle = document.getElementById("appChatHeaderTitle");
    var backBtn = document.getElementById("appChatBackBtn");
    var newBtn = document.getElementById("appChatNewBtn");
    var replyForm = document.getElementById("appChatReplyForm");
    var replyInput = document.getElementById("appChatReplyInput");
    var composeForm = document.getElementById("appChatComposeForm");
    var targetType = document.getElementById("appChatTargetType");
    var usersWrap = document.getElementById("appChatUsersWrap");
    var roleWrap = document.getElementById("appChatRoleWrap");
    var usersSelect = document.getElementById("appChatUsersSelect");
    var roleSelect = document.getElementById("appChatRoleSelect");
    var composeBody = document.getElementById("appChatComposeBody");
    var composeError = document.getElementById("appChatComposeError");
    var badge = document.getElementById("appChatBadge");

    function setBadge(count) {
      var n = parseInt(count, 10) || 0;
      if (n <= 0) {
        if (badge) badge.remove();
        btn.setAttribute("aria-label", "Chat interno");
        return;
      }
      if (!badge) {
        var span = document.createElement("span");
        span.className = "app-chat-badge";
        span.id = "appChatBadge";
        span.setAttribute("aria-hidden", "true");
        btn.appendChild(span);
        badge = span;
      }
      badge.textContent = n < 10 ? String(n) : "9+";
      btn.setAttribute("aria-label", "Chat interno (" + n + " sin leer)");
    }

    function showView(name) {
      state.view = name;
      listView.classList.toggle("d-none", name !== "list");
      threadView.classList.toggle("d-none", name !== "thread");
      composeView.classList.toggle("d-none", name !== "compose");
      backBtn.classList.toggle("d-none", name === "list");
      if (name === "list") {
        headerTitle.textContent = "Chat interno";
        newBtn.classList.remove("d-none");
      } else if (name === "thread") {
        headerTitle.textContent = (state.activeThread && state.activeThread.title) || "Conversación";
        newBtn.classList.add("d-none");
      } else {
        headerTitle.textContent = "Nuevo mensaje";
        newBtn.classList.add("d-none");
      }
    }

    function renderThreadList() {
      if (!state.threads.length) {
        threadList.innerHTML = '<div class="dropdown-item-text text-muted small px-3 py-3">No hay conversaciones. Usá «Nuevo mensaje» para escribir a alguien o a un perfil.</div>';
        return;
      }
      threadList.innerHTML = state.threads.map(function (t) {
        var unread = parseInt(t.unread_count, 10) > 0;
        return (
          '<button type="button" class="app-chat-thread-item' + (unread ? " app-chat-thread-item--unread" : "") + '" data-thread-id="' + t.id + '">' +
          '<div class="d-flex justify-content-between gap-2"><span class="app-chat-thread-title">' + escapeHtml(t.title) + "</span>" +
          (unread ? '<span class="badge rounded-pill text-bg-primary">' + t.unread_count + "</span>" : "") +
          "</div>" +
          '<div class="app-chat-thread-preview">' + escapeHtml(t.last_message_preview || "") + "</div>" +
          '<div class="small text-muted mt-1">' + escapeHtml(formatTime(t.last_message_at)) + "</div>" +
          "</button>"
        );
      }).join("");
      qsa(".app-chat-thread-item", threadList).forEach(function (el) {
        el.addEventListener("click", function () {
          openThread(parseInt(el.getAttribute("data-thread-id"), 10));
        });
      });
    }

    function loadThreads() {
      var url = menu.getAttribute("data-threads-url");
      threadList.innerHTML = '<div class="dropdown-item-text text-muted small px-3 py-3">Cargando conversaciones…</div>';
      return jsonFetch(url, { method: "GET" }, menu).then(function (data) {
        state.threads = data.threads || [];
        setBadge(data.unread_total || 0);
        renderThreadList();
      }).catch(function () {
        threadList.innerHTML = '<div class="dropdown-item-text text-danger small px-3 py-3">No se pudieron cargar las conversaciones.</div>';
      });
    }

    function renderMessages(messages) {
      if (!messages || !messages.length) {
        messagesEl.innerHTML = '<div class="text-muted small text-center py-3">Sin mensajes todavía.</div>';
        return;
      }
      messagesEl.innerHTML = messages.map(function (m) {
        var cls = m.is_mine ? "app-chat-msg--mine" : "app-chat-msg--other";
        return (
          '<div class="app-chat-msg ' + cls + '">' +
          '<div class="app-chat-msg-meta">' + escapeHtml(m.sender_label) + " · " + escapeHtml(formatTime(m.created_at)) + "</div>" +
          escapeHtml(m.body) +
          "</div>"
        );
      }).join("");
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function openThread(threadId) {
      state.activeThreadId = threadId;
      state.activeThread = state.threads.find(function (t) { return t.id === threadId; }) || null;
      showView("thread");
      messagesEl.innerHTML = '<div class="text-muted small text-center py-3">Cargando…</div>';
      var url = menu.getAttribute("data-threads-url").replace(/\/api\/threads\/?$/, "/api/threads/" + threadId + "/messages");
      jsonFetch(url, { method: "GET" }, menu).then(function (data) {
        state.activeThread = data.thread || state.activeThread;
        headerTitle.textContent = (state.activeThread && state.activeThread.title) || "Conversación";
        renderMessages(data.messages || []);
        var last = (data.messages || []).slice(-1)[0];
        if (last) {
          var readUrl = url.replace(/\/messages$/, "/read");
          jsonFetch(readUrl, { method: "POST", body: JSON.stringify({ up_to_message_id: last.id }) }, menu)
            .then(function (rd) { setBadge(rd.unread_total || 0); loadThreads(); })
            .catch(function () {});
        }
      }).catch(function () {
        messagesEl.innerHTML = '<div class="text-danger small text-center py-3">No se pudo abrir la conversación.</div>';
      });
    }

    function loadRecipients() {
      if (state.recipientsLoaded) return Promise.resolve();
      var url = menu.getAttribute("data-recipients-url");
      return jsonFetch(url, { method: "GET" }, menu).then(function (data) {
        usersSelect.innerHTML = (data.users || []).map(function (u) {
          return '<option value="' + u.id + '">' + escapeHtml(u.label) + " (" + escapeHtml(u.rol_label) + ")</option>";
        }).join("");
        roleSelect.innerHTML = (data.roles || []).map(function (r) {
          return '<option value="' + escapeHtml(r.value) + '">' + escapeHtml(r.label) + "</option>";
        }).join("");
        state.recipientsLoaded = true;
      });
    }

    function syncTargetFields() {
      var isRole = targetType.value === "role";
      usersWrap.classList.toggle("d-none", isRole);
      roleWrap.classList.toggle("d-none", !isRole);
    }

    if (targetType) targetType.addEventListener("change", syncTargetFields);

    if (newBtn) {
      newBtn.addEventListener("click", function () {
        composeError.classList.add("d-none");
        composeBody.value = "";
        loadRecipients().then(function () {
          syncTargetFields();
          showView("compose");
        });
      });
    }

    if (backBtn) {
      backBtn.addEventListener("click", function () {
        if (state.view === "thread" || state.view === "compose") {
          showView("list");
          loadThreads();
        }
      });
    }

    if (replyForm) {
      replyForm.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var body = (replyInput.value || "").trim();
        if (!body || !state.activeThreadId) return;
        var url = menu.getAttribute("data-threads-url").replace(/\/api\/threads\/?$/, "/api/threads/" + state.activeThreadId + "/messages");
        jsonFetch(url, { method: "POST", body: JSON.stringify({ body: body }) }, menu)
          .then(function (data) {
            replyInput.value = "";
            openThread(state.activeThreadId);
          })
          .catch(function () {});
      });
    }

    if (composeForm) {
      composeForm.addEventListener("submit", function (ev) {
        ev.preventDefault();
        composeError.classList.add("d-none");
        var body = (composeBody.value || "").trim();
        if (!body) {
          composeError.textContent = "Escribí un mensaje.";
          composeError.classList.remove("d-none");
          return;
        }
        var payload = { body: body };
        if (targetType.value === "role") {
          payload.target_role = roleSelect.value;
        } else {
          payload.target_user_ids = qsa("#appChatUsersSelect option:checked").map(function (o) { return parseInt(o.value, 10); });
          if (!payload.target_user_ids.length) {
            composeError.textContent = "Elegí al menos un usuario.";
            composeError.classList.remove("d-none");
            return;
          }
        }
        var url = menu.getAttribute("data-threads-url");
        jsonFetch(url, { method: "POST", body: JSON.stringify(payload) }, menu)
          .then(function (data) {
            var tid = data.thread && data.thread.id;
            loadThreads().then(function () {
              if (tid) openThread(tid);
              else showView("list");
            });
          })
          .catch(function (err) {
            composeError.textContent = (err.payload && err.payload.message) || "No se pudo enviar el mensaje.";
            composeError.classList.remove("d-none");
          });
      });
    }

    bootstrap.Dropdown.getOrCreateInstance(btn, {
      popperConfig: function (defaultConfig) {
        var mods = (defaultConfig.modifiers || []).map(function (m) {
          if (m.name === "computeStyles") {
            return { name: "computeStyles", options: Object.assign({}, m.options || {}, { gpuAcceleration: false }) };
          }
          return m;
        });
        return Object.assign({}, defaultConfig, { strategy: "fixed", modifiers: mods });
      },
    });

    btn.addEventListener("show.bs.dropdown", function () {
      showView("list");
      loadThreads();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initInternalChat);
  } else {
    initInternalChat();
  }
})();
