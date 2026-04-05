document.addEventListener("DOMContentLoaded", function () {
  const searchInput = document.getElementById("cloudchat-user-search");
  const userCards = Array.from(document.querySelectorAll("[data-cloudchat-user-card]"));
  const emptyState = document.getElementById("cloudchat-user-search-empty");
  const messageInput = document.querySelector("[data-cloudchat-message-input]");
  const messageCount = document.querySelector("[data-cloudchat-message-count]");
  const threadRoot = document.querySelector("[data-cloudchat-thread]");
  const chatFeed = document.querySelector("[data-cloudchat-feed]");
  const threadCount = document.querySelector("[data-cloudchat-thread-count]");
  const passwordPreviewInput = document.querySelector("[data-password-preview-input]");
  const passwordPreviewToggle = document.querySelector("[data-password-preview-toggle]");
  const passwordPreviewCopy = document.querySelector("[data-password-preview-copy]");

  if (passwordPreviewInput && passwordPreviewToggle) {
    passwordPreviewToggle.addEventListener("click", function () {
      const revealing = passwordPreviewInput.type === "text";
      passwordPreviewInput.type = revealing ? "password" : "text";
      passwordPreviewToggle.textContent = revealing ? "Reveal" : "Hide";
    });
  }

  if (passwordPreviewInput && passwordPreviewCopy) {
    passwordPreviewCopy.addEventListener("click", async function () {
      try {
        await window.navigator.clipboard.writeText(passwordPreviewInput.value);
        passwordPreviewCopy.textContent = "Copied";
        window.setTimeout(function () {
          passwordPreviewCopy.textContent = "Copy";
        }, 1400);
      } catch (error) {
        passwordPreviewCopy.textContent = "Copy failed";
        window.setTimeout(function () {
          passwordPreviewCopy.textContent = "Copy";
        }, 1400);
      }
    });
  }

  if (messageInput && messageCount) {
    const syncMessageCount = function () {
      const limit = Number(messageInput.getAttribute("maxlength") || "0");
      const used = messageInput.value.length;
      messageCount.textContent = used + " / " + limit;
    };

    messageInput.addEventListener("input", syncMessageCount);
    syncMessageCount();
  }

  if (chatFeed) {
    chatFeed.scrollTop = chatFeed.scrollHeight;
  }

  if (threadRoot && chatFeed) {
    const liveUrl = threadRoot.dataset.cloudchatLiveUrl || "";
    const currentUserId = Number(threadRoot.dataset.cloudchatCurrentUserId || "0");
    const partnerName = threadRoot.dataset.cloudchatPartnerName || "this user";
    let lastMessageId = Number(threadRoot.dataset.cloudchatLastMessageId || "0");
    let liveRequestInFlight = false;

    const isNearBottom = function () {
      return chatFeed.scrollHeight - chatFeed.scrollTop - chatFeed.clientHeight < 80;
    };

    const syncThreadCount = function (count) {
      if (!threadCount) {
        return;
      }
      threadCount.textContent = count + " message" + (count === 1 ? "" : "s") + " with " + partnerName;
    };

    const createMessageRow = function (message, previousAuthorId) {
      const ownMessage = Number(message.author_id) === currentUserId;
      const compact = previousAuthorId === Number(message.author_id);
      const row = document.createElement("article");
      row.className =
        "cloudchat-message-row " +
        (ownMessage ? "cloudchat-message-row-own " : "cloudchat-message-row-peer ") +
        (compact ? "cloudchat-message-row-compact" : "");
      row.dataset.messageId = String(message.id);
      row.dataset.authorId = String(message.author_id);

      const avatar = document.createElement("div");
      avatar.className = "cloudchat-message-avatar";
      avatar.setAttribute("aria-hidden", "true");
      avatar.textContent = (ownMessage ? "Y" : String(message.author_username || "?").slice(0, 1)).toUpperCase();

      const content = document.createElement("div");
      content.className = "cloudchat-message-content";

      if (!compact) {
        const head = document.createElement("div");
        head.className = "cloudchat-message-head";

        const author = document.createElement("span");
        author.className = "cloudchat-message-author";
        author.textContent = message.author_username + (ownMessage ? " · You" : "");

        const time = document.createElement("span");
        time.className = "cloudchat-message-time";
        time.textContent = message.created_at + " UTC";

        head.append(author, time);
        content.append(head);
      }

      const body = document.createElement("p");
      body.className = "cloudchat-message-body";
      body.textContent = message.message_text;

      content.append(body);
      row.append(avatar, content);
      return row;
    };

    const renderMessages = function (messages) {
      const stickToBottom = isNearBottom();
      chatFeed.replaceChildren();

      if (!messages.length) {
        const empty = document.createElement("div");
        empty.className = "cloudchat-thread-empty";
        empty.dataset.cloudchatThreadEmpty = "true";
        empty.textContent = "No messages yet. Start the DM.";
        chatFeed.append(empty);
        syncThreadCount(0);
        return;
      }

      let previousAuthorId = null;
      messages.forEach(function (message) {
        const row = createMessageRow(message, previousAuthorId);
        chatFeed.append(row);
        previousAuthorId = Number(message.author_id);
      });

      syncThreadCount(messages.length);

      if (stickToBottom) {
        chatFeed.scrollTop = chatFeed.scrollHeight;
      }
    };

    const pollLiveThread = async function () {
      if (!liveUrl || liveRequestInFlight) {
        return;
      }

      liveRequestInFlight = true;

      try {
        const response = await window.fetch(liveUrl, {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
          cache: "no-store",
        });

        if (!response.ok) {
          return;
        }

        const payload = await response.json();
        const latestMessageId = Number(payload.latest_message_id || "0");
        if (latestMessageId === lastMessageId && chatFeed.children.length) {
          return;
        }

        renderMessages(Array.isArray(payload.messages) ? payload.messages : []);
        lastMessageId = latestMessageId;
        threadRoot.dataset.cloudchatLastMessageId = String(latestMessageId);
      } catch (error) {
        return;
      } finally {
        liveRequestInFlight = false;
      }
    };

    window.setInterval(pollLiveThread, 2500);
  }

  if (!searchInput || !userCards.length) {
    return;
  }

  const filterUsers = function () {
    const query = searchInput.value.trim().toLowerCase();
    let visibleCount = 0;

    userCards.forEach(function (card) {
      const haystack = card.dataset.cloudchatUserSearch || "";
      const visible = !query || haystack.includes(query);
      card.style.display = visible ? "" : "none";
      if (visible) {
        visibleCount += 1;
      }
    });

    if (emptyState) {
      emptyState.classList.toggle("empty-hidden", visibleCount > 0);
    }
  };

  searchInput.addEventListener("input", filterUsers);
  filterUsers();
});
