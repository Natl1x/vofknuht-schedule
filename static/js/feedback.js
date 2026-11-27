(() => {
  const form = document.querySelector("#feedback-form");
  if (!form) return;

  const list = document.querySelector("#feedback-list");
  const count = document.querySelector("#feedback-count");
  const loading = document.querySelector("#feedback-loading");
  const status = document.querySelector("#feedback-status");
  const submit = form.querySelector('button[type="submit"]');
  const apiUrl = form.dataset.apiUrl;

  function showStatus(message, kind) {
    status.textContent = message;
    status.className = `feedback-status ${kind}`;
    status.setAttribute("role", kind === "error" ? "alert" : "status");
    status.hidden = false;
  }

  async function request(url, options) {
    const response = await fetch(url, options);
    let body;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    if (!response.ok) {
      throw new Error(
        body?.error?.message || `Сервер повернув помилку ${response.status}.`,
      );
    }
    if (!body) throw new Error("Сервер надіслав порожню відповідь.");
    return body;
  }

  function render(items) {
    list.replaceChildren();
    count.textContent = String(items.length);
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "notice";
      empty.textContent = "Відгуків поки немає.";
      list.append(empty);
      return;
    }
    for (const item of items) {
      const card = document.createElement("article");
      card.className = "card feedback-item";
      const title = document.createElement("h3");
      title.textContent = item.name;
      const message = document.createElement("p");
      message.textContent = item.message;
      const date = document.createElement("small");
      date.textContent = item.created_at;
      card.append(title, message, date);
      list.append(card);
    }
  }

  async function loadFeedback() {
    loading.hidden = false;
    try {
      const data = await request(apiUrl, {
        headers: { Accept: "application/json" },
      });
      render(data.feedback);
    } catch (error) {
      showStatus(`Не вдалося оновити відгуки: ${error.message}`, "error");
    } finally {
      loading.hidden = true;
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(form));
    for (const key of Object.keys(data)) data[key] = data[key].trim();
    if (data.name.length < 2 || !data.email || !data.message) {
      showStatus("Перевірте ім’я, email і текст повідомлення.", "error");
      return;
    }
    submit.disabled = true;
    submit.textContent = "Надсилаємо…";
    try {
      await request(apiUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(data),
      });
      form.reset();
      showStatus("Дякуємо! Відгук додано.", "success");
      await loadFeedback();
    } catch (error) {
      showStatus(`Не вдалося надіслати відгук: ${error.message}`, "error");
    } finally {
      submit.disabled = false;
      submit.textContent = "Надіслати";
    }
  });

  loadFeedback();
})();
