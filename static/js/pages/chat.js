document.addEventListener("DOMContentLoaded", function () {
  const searchInput = document.getElementById("cloudchat-user-search");
  const userCards = Array.from(document.querySelectorAll("[data-cloudchat-user-card]"));
  const emptyState = document.getElementById("cloudchat-user-search-empty");
  const messageInput = document.querySelector("[data-cloudchat-message-input]");
  const messageCount = document.querySelector("[data-cloudchat-message-count]");
  const composeForm = document.querySelector("[data-cloudchat-compose-form]");
  const threadRoot = document.querySelector("[data-cloudchat-thread]");
  const chatFeed = document.querySelector("[data-cloudchat-feed]");
  const threadCount = document.querySelector("[data-cloudchat-thread-count]");
  const partnerStatusText = document.querySelector("[data-cloudchat-partner-status-text]");
  const partnerStatusDot = document.querySelector("[data-cloudchat-partner-status-dot]");
  const partnerListRoot = document.querySelector("[data-cloudchat-partner-list-root]");
  const partnerList = document.querySelector("[data-cloudchat-partner-list]");
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

  const syncMessageCount = function () {
    if (!messageInput || !messageCount) {
      return;
    }
    const limit = Number(messageInput.getAttribute("maxlength") || "0");
    const used = messageInput.value.length;
    messageCount.textContent = used + " / " + limit;
  };

  const autosizeMessageInput = function () {
    if (!messageInput) {
      return;
    }
    messageInput.style.height = "0px";
    messageInput.style.height = Math.min(messageInput.scrollHeight, window.innerHeight * 0.42) + "px";
  };

  if (messageInput) {
    messageInput.addEventListener("input", function () {
      syncMessageCount();
      autosizeMessageInput();
    });

    messageInput.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        if (composeForm && messageInput.value.trim()) {
          composeForm.requestSubmit();
        }
      }
    });

    syncMessageCount();
    autosizeMessageInput();
  }

  if (chatFeed) {
    chatFeed.scrollTop = chatFeed.scrollHeight;
  }

  if (threadRoot && chatFeed) {
    const liveUrl = threadRoot.dataset.cloudchatLiveUrl || "";
    const currentUserId = Number(threadRoot.dataset.cloudchatCurrentUserId || "0");
    const selectedPartnerId = Number(threadRoot.dataset.cloudchatPartnerId || "0");
    const partnerName = threadRoot.dataset.cloudchatPartnerName || "this user";
    const threadBase = partnerListRoot ? partnerListRoot.dataset.cloudchatThreadBase || "/chat/" : "/chat/";
    let lastMessageId = Number(threadRoot.dataset.cloudchatLastMessageId || "0");
    let liveRequestInFlight = false;

    const statusText = function (status) {
      if (status === "online") {
        return "Active now";
      }
      if (status === "idle") {
        return "Idle";
      }
      return "Offline";
    };

    const shortTime = function (timestamp) {
      if (!timestamp || String(timestamp).length < 16) {
        return "";
      }
      return String(timestamp).slice(11, 16);
    };

    const isNearBottom = function () {
      return chatFeed.scrollHeight - chatFeed.scrollTop - chatFeed.clientHeight < 96;
    };

    const syncThreadCount = function (count) {
      if (!threadCount) {
        return;
      }
      threadCount.textContent = count + " message" + (count === 1 ? "" : "s");
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
        time.textContent = message.created_at;

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
        empty.textContent = "No messages yet. Say hello.";
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

    const createPartnerLink = function (partner) {
      const link = document.createElement("a");
      link.className = "cloudchat-dm-link" + (Number(partner.id) === selectedPartnerId ? " cloudchat-dm-link-selected" : "");
      link.href = threadBase + "?dm=" + encodeURIComponent(partner.id);
      link.dataset.partnerId = String(partner.id);

      const avatarWrap = document.createElement("div");
      avatarWrap.className = "cloudchat-dm-avatar-wrap";

      const avatar = document.createElement("div");
      avatar.className = "cloudchat-dm-avatar";
      avatar.textContent = String(partner.username || "?").slice(0, 2).toUpperCase();

      const status = document.createElement("span");
      status.className = "cloudchat-status-dot cloudchat-status-dot-" + (partner.status || "offline");

      avatarWrap.append(avatar, status);

      const copy = document.createElement("div");
      copy.className = "cloudchat-dm-copy";

      const topLine = document.createElement("div");
      topLine.className = "cloudchat-dm-line";

      const name = document.createElement("span");
      name.className = "cloudchat-dm-name";
      name.textContent = partner.username;

      topLine.append(name);

      if (partner.latest_at) {
        const time = document.createElement("span");
        time.className = "cloudchat-dm-time";
        time.textContent = shortTime(partner.latest_at);
        topLine.append(time);
      }

      const bottomLine = document.createElement("div");
      bottomLine.className = "cloudchat-dm-line";

      const preview = document.createElement("span");
      preview.className = "cloudchat-dm-preview";
      if (partner.latest_preview) {
        preview.textContent = (partner.latest_from_current ? "You: " : "") + partner.latest_preview;
      } else {
        preview.textContent = "Start a conversation";
      }

      bottomLine.append(preview);

      if (Number(partner.unread_count || 0) > 0 && Number(partner.id) !== selectedPartnerId) {
        const unread = document.createElement("span");
        unread.className = "cloudchat-unread-badge";
        unread.textContent = String(partner.unread_count);
        bottomLine.append(unread);
      }

      copy.append(topLine, bottomLine);
      link.append(avatarWrap, copy);
      return link;
    };

    const renderPartners = function (partners) {
      if (!partnerList) {
        return;
      }

      partnerList.replaceChildren();
      partners.forEach(function (partner) {
        partnerList.append(createPartnerLink(partner));
      });
    };

    const syncPartnerPresence = function (partner) {
      if (partnerStatusText) {
        partnerStatusText.textContent = statusText(partner.status);
      }
      if (partnerStatusDot) {
        partnerStatusDot.className = "cloudchat-status-dot cloudchat-status-dot-" + (partner.status || "offline");
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

        if (Array.isArray(payload.partners)) {
          renderPartners(payload.partners);
        }

        if (payload.partner) {
          syncPartnerPresence(payload.partner);
        }

        const latestMessageId = Number(payload.latest_message_id || "0");
        if (latestMessageId !== lastMessageId || !chatFeed.children.length) {
          renderMessages(Array.isArray(payload.messages) ? payload.messages : []);
          lastMessageId = latestMessageId;
          threadRoot.dataset.cloudchatLastMessageId = String(latestMessageId);
        } else if (typeof payload.message_count === "number") {
          syncThreadCount(payload.message_count);
        }
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
