(() => {
    if (location.origin !== 'https://web.gemspace.com') { alert('q: откройте https://web.gemspace.com/'); return; }
    if (window.__qInstalled) { alert(window.q ? 'q уже запущен. Перейдите в другой чат и обратно, если кнопок нет.' : 'q: обновите страницу после незавершённого запуска.'); return; }
    if (window.__qBookmarklet?.phase === 'starting') return;
    // A timed-out script must not initialize later, after a failed load.
    if (document.currentScript && window.__qBookmarklet?.phase === 'failed') return;
    const state = window.__qBookmarklet = {phase:'starting'};
    const fail = () => { state.phase='failed'; alert('q: ошибка инициализации. Возможны CSP/Trusted Types. Обновите страницу перед повторным запуском.'); };
    try {
      const result = (async () => {
  'use strict';

  // ============================================================
  // q — Gemspace transcription
  // VoiceMessage + CircleVideo
  //
  // Railway:
  // https://voice-recognision-server-production.up.railway.app
  //
  // UI:
  //
  // [ q ]    ← qwerty was here
  //
  // Credit is mounted directly into document.body,
  // so Gemspace message overflow cannot clip it.
  // ============================================================

  const Q_API =
    'https://voice-recognision-server-production.up.railway.app';


  // ============================================================
  // Prevent duplicate installation
  // ============================================================

  if (window.__qInstalled) {
    console.log('[q] already installed');
    return;
  }

  window.__qInstalled = true;


  const mediaMap = new Map();


  // ============================================================
  // CSS
  // ============================================================

  const oldStyle =
    document.getElementById('q-style');

  if (oldStyle) {
    oldStyle.remove();
  }


  const style =
    document.createElement('style');

  style.id = 'q-style';

  style.textContent = `
    /* ========================================================
       q label
       ======================================================== */

    .q-label {
      width: 100%;
      height: 100%;

      display: flex;
      align-items: center;
      justify-content: center;

      font-family:
        -apple-system,
        BlinkMacSystemFont,
        "SF Pro Display",
        "Segoe UI",
        sans-serif;

      font-size: 20px;
      font-weight: 700;
      line-height: 1;

      user-select: none;
      pointer-events: none;
    }


    /* ========================================================
       CREDIT

       This element lives directly under document.body.

       It is NOT inside the Gemspace message.

       [q]      ← qwerty was here
                 ^^^^^^^^^^^^^^^^^^
       ======================================================== */

    .q-credit {
      position: fixed;

      z-index: 2147483647;

      display: flex;
      align-items: center;

      width: max-content;

      font-family:
        -apple-system,
        BlinkMacSystemFont,
        "SF Pro Text",
        "Segoe UI",
        sans-serif;

      font-size: 12px;
      font-weight: 600;
      line-height: 1;

      color:
        rgba(255, 255, 255, 0.72);

      white-space: nowrap;

      pointer-events: none;
      user-select: none;

      opacity: 0.88;

      text-shadow:
        0 1px 3px
        rgba(0, 0, 0, 0.75);

      transition:
        opacity 120ms ease;
    }


    .q-credit-arrow {
      display: inline-block;

      margin-right: 5px;

      font-size: 16px;
      font-weight: 600;
      line-height: 1;

      color:
        rgba(255, 255, 255, 0.86);
    }


    /* ========================================================
       Transcript
       ======================================================== */

    .q-transcript {
      display: block;

      box-sizing: border-box;

      width: 100%;
      max-width: 520px;

      margin-top: 8px;
      padding: 8px 12px 10px;

      font-family:
        -apple-system,
        BlinkMacSystemFont,
        "SF Pro Text",
        "Segoe UI",
        sans-serif;

      font-size: 14px;
      font-weight: 400;
      line-height: 1.4;

      --q-transcript-fallback: #1f1f21;
      color: var(--incoming-bubble-text-primary, var(--base-110, var(--q-transcript-fallback)));

      white-space: pre-wrap;
      overflow-wrap: anywhere;

      cursor: text;
      user-select: text;
    }


    :root[data-theme="dark"] .q-transcript {
      --q-transcript-fallback: #fcfcfc;
    }


    .q-transcript[hidden] {
      display: none !important;
    }


    /* ========================================================
       Circle overlay
       ======================================================== */

    .q-circle-overlay {
      position: absolute;

      width: 38px;
      height: 38px;

      z-index: 1000;

      pointer-events: none;
    }


    .q-circle-overlay[hidden] {
      display: none !important;
    }


    /* ========================================================
       Circle button
       ======================================================== */

    .q-circle-button {
      width: 38px;
      height: 38px;

      display: flex;
      align-items: center;
      justify-content: center;

      padding: 0;
      margin: 0;

      border: 0;
      border-radius: 50%;

      background:
        rgba(24, 24, 27, 0.78);

      color: #ffffff;

      cursor: pointer;

      pointer-events: auto;

      box-shadow:
        0 2px 12px
        rgba(0, 0, 0, 0.30);

      backdrop-filter:
        blur(10px);

      -webkit-backdrop-filter:
        blur(10px);

      transition:
        transform 120ms ease,
        background 120ms ease;
    }


    .q-circle-button:hover {
      transform: scale(1.07);

      background:
        rgba(24, 24, 27, 0.92);
    }


    .q-circle-button:active {
      transform: scale(0.93);
    }


    .q-circle-button .q-label {
      font-size: 19px;
    }
  `;


  (
    document.head ||
    document.documentElement
  ).appendChild(style);


  // ============================================================
  // Credit
  // ============================================================

  function createCredit(messageId) {
    const existing =
      document.querySelector(
        `.q-credit[data-q-for="${CSS.escape(
          String(messageId)
        )}"]`
      );


    if (existing) {
      return existing;
    }


    const credit =
      document.createElement('div');


    credit.className =
      'q-credit';


    credit.dataset.qFor =
      String(messageId);


    credit.innerHTML = `
      <span class="q-credit-arrow">←</span>
      <span>qwerty was here</span>
    `;


    /*
     * IMPORTANT:
     *
     * Mount directly into BODY.
     *
     * This means overflow:hidden on the
     * Gemspace message cannot clip us.
     */

    document.body.appendChild(
      credit
    );


    return credit;
  }


  function positionCredit(
    button,
    credit
  ) {
    if (
      !button ||
      !credit ||
      !button.isConnected
    ) {
      if (credit) {
        credit.style.display =
          'none';
      }

      return;
    }


    const rect =
      button.getBoundingClientRect();


    /*
     * If button is outside viewport,
     * hide the floating credit.
     */

    const visible =
      rect.width > 0 &&
      rect.height > 0 &&
      rect.bottom > 0 &&
      rect.right > 0 &&
      rect.top <
        window.innerHeight &&
      rect.left <
        window.innerWidth;


    if (!visible) {
      credit.style.display =
        'none';

      return;
    }


    credit.style.display =
      'flex';


    /*
     * THIS controls horizontal distance.
     *
     * q [------24px------] ← qwerty was here
     */

    const gap = 24;


    credit.style.left =
      `${rect.right + gap}px`;


    credit.style.top =
      `${
        rect.top +
        rect.height / 2
      }px`;


    credit.style.transform =
      'translateY(-50%)';
  }


  // ============================================================
  // Media detection
  // ============================================================

  function getMediaType(payload) {
    if (!payload) {
      return null;
    }


    const payloadType =
      payload.payloadType;


    const javaType =
      payload['@type'];


    if (
      payloadType ===
        'VoiceMessage' ||
      javaType ===
        'PayloadRs$VoiceRs'
    ) {
      return 'voice';
    }


    if (
      payloadType ===
        'CircleVideo' ||
      javaType ===
        'PayloadRs$CircleVideoRs'
    ) {
      return 'circle';
    }


    return null;
  }


  function extractMedia(value) {
    if (
      !value ||
      typeof value !== 'object'
    ) {
      return null;
    }


    const payload =
      value.payload;


    if (
      !payload ||
      typeof payload !== 'object'
    ) {
      return null;
    }


    const mediaType =
      getMediaType(payload);


    if (!mediaType) {
      return null;
    }


    if (
      !value.id ||
      !payload.url
    ) {
      return null;
    }


    return {
      id:
        String(value.id),

      clientUuid:
        value.clientUuid ?? null,

      mediaType,

      url:
        payload.url,

      fileName:
        payload.fileName ?? null,

      mimeType:
        payload.mimeType ?? null,

      duration:
        payload.duration ?? null
    };
  }


  function collectMedia(
    value,
    output = []
  ) {
    if (
      !value ||
      typeof value !== 'object'
    ) {
      return output;
    }


    if (Array.isArray(value)) {
      for (const item of value) {
        collectMedia(
          item,
          output
        );
      }

      return output;
    }


    const media =
      extractMedia(value);


    if (media) {
      output.push(media);
    }


    for (
      const child of
      Object.values(value)
    ) {
      if (
        child &&
        typeof child === 'object'
      ) {
        collectMedia(
          child,
          output
        );
      }
    }


    return output;
  }


  function registerMedia(items) {
    let changed = false;


    for (const media of items) {
      if (!media?.id) {
        continue;
      }


      mediaMap.set(
        String(media.id),
        media
      );


      changed = true;
    }


    if (!changed) {
      return;
    }


    console.log(
      '[q] media map',
      mediaMap
    );


    scheduleRender();
  }


  // ============================================================
  // Fetch interception
  // ============================================================

  const originalFetch =
    window.fetch.bind(window);


  window.fetch =
    async (...args) => {

      const response =
        await originalFetch(...args);


      try {
        const clone =
          response.clone();


        const contentType =
          clone.headers.get(
            'content-type'
          ) ?? '';


        if (
          contentType.includes(
            'application/json'
          )
        ) {
          clone
            .json()
            .then((json) => {

              const media =
                collectMedia(json);


              if (media.length) {
                registerMedia(
                  media
                );
              }
            })
            .catch(() => {});
        }
      } catch (error) {
        console.debug(
          '[q] response inspection failed',
          error
        );
      }


      return response;
    };


  console.log(
    '[q] fetch interceptor installed'
  );


  // ============================================================
  // Media URL
  // ============================================================

  function buildMediaUrl(media) {
    const url =
      new URL(media.url);


    if (
      media.clientUuid &&
      !url.searchParams.has('id')
    ) {
      url.searchParams.set(
        'id',
        media.clientUuid
      );
    }


    return url.toString();
  }


  // ============================================================
  // Download media
  // ============================================================

  async function downloadMedia(
    media
  ) {
    const url =
      buildMediaUrl(media);


    console.log(
      '[q] downloading',
      {
        id: media.id,
        type:
          media.mediaType,
        url
      }
    );


    const response =
      await originalFetch(url);


    if (!response.ok) {
      throw new Error(
        `Media download failed: ${response.status}`
      );
    }


    const blob =
      await response.blob();


    console.log(
      '[q] downloaded',
      {
        id:
          media.id,

        type:
          media.mediaType,

        size:
          blob.size,

        blobType:
          blob.type
      }
    );


    return blob;
  }


  // ============================================================
  // Railway transcription
  // ============================================================

  async function transcribe(
    media
  ) {
    const blob =
      await downloadMedia(
        media
      );


    const form =
      new FormData();


    const fallbackName =
      media.mediaType ===
      'circle'
        ? 'circle.mp4'
        : 'voice.m4a';


    form.append(
      'file',
      blob,
      media.fileName ??
        fallbackName
    );


    console.log(
      '[q] sending to Railway',
      {
        api:
          Q_API,

        id:
          media.id,

        type:
          media.mediaType,

        fileName:
          media.fileName ??
          fallbackName,

        mimeType:
          media.mimeType,

        blobType:
          blob.type,

        size:
          blob.size
      }
    );


    const response =
      await originalFetch(
        `${Q_API}/transcribe`,
        {
          method: 'POST',
          body: form
        }
      );


    let result = null;


    try {
      result =
        await response.json();
    } catch {}


    if (!response.ok) {
      const detail =
        result?.detail;


      const code =
        detail?.code;


      if (
        code ===
        'gemini_content_blocked'
      ) {
        throw new Error(
          'Gemini blocked this media'
        );
      }


      throw new Error(
        detail?.message ??
        `Backend error: ${response.status}`
      );
    }


    if (
      typeof result?.text !==
      'string'
    ) {
      throw new Error(
        'Backend returned no transcription'
      );
    }


    return result;
  }


  // ============================================================
  // Transcript helpers
  // ============================================================

  function createTranscriptBox() {
    const box =
      document.createElement(
        'div'
      );


    box.className =
      'q-transcript';


    box.hidden = true;


    return box;
  }


  function getExistingTranscript(
    message
  ) {
    return message.querySelector(
      '.q-transcript'
    );
  }


  // ============================================================
  // Voice transcript
  // ============================================================

  function getVoiceTranscriptBox(
    message,
    button
  ) {
    const existing =
      getExistingTranscript(
        message
      );


    if (existing) {
      return existing;
    }


    const voiceRow =
      button.parentElement;


    if (!voiceRow) {
      throw new Error(
        'Voice row not found'
      );
    }


    const box =
      createTranscriptBox();


    voiceRow.insertAdjacentElement(
      'afterend',
      box
    );


    return box;
  }


  // ============================================================
  // Circle video block
  // ============================================================

  function findCircleVideoBlock(
    message
  ) {
    const images = [
      ...message.querySelectorAll(
        'img'
      )
    ];


    let bestImage = null;
    let bestImageArea = 0;


    for (const image of images) {
      const rect =
        image.getBoundingClientRect();


      const area =
        rect.width *
        rect.height;


      if (
        rect.width < 150 ||
        rect.height < 150
      ) {
        continue;
      }


      if (
        area >
        bestImageArea
      ) {
        bestImageArea =
          area;

        bestImage =
          image;
      }
    }


    if (bestImage) {
      const videoButton =
        bestImage.closest(
          '[role="button"]'
        );


      if (
        videoButton?.parentElement
      ) {
        return (
          videoButton.parentElement
        );
      }
    }


    /*
     * Fallback for broken / unloaded
     * CircleVideo preview.
     */

    const buttons = [
      ...message.querySelectorAll(
        '[role="button"]'
      )
    ];


    let bestButton = null;
    let bestButtonArea = 0;


    for (const button of buttons) {
      if (
        button === message
      ) {
        continue;
      }


      if (
        button.closest(
          '.q-circle-overlay'
        )
      ) {
        continue;
      }


      const rect =
        button.getBoundingClientRect();


      const area =
        rect.width *
        rect.height;


      if (
        rect.width < 150 ||
        rect.height < 150
      ) {
        continue;
      }


      if (
        area >
        bestButtonArea
      ) {
        bestButtonArea =
          area;

        bestButton =
          button;
      }
    }


    return (
      bestButton?.parentElement ??
      null
    );
  }


  // ============================================================
  // Circle transcript
  // ============================================================

  function getCircleTranscriptBox(
    message
  ) {
    const existing =
      getExistingTranscript(
        message
      );


    if (existing) {
      return existing;
    }


    const box =
      createTranscriptBox();


    const videoBlock =
      findCircleVideoBlock(
        message
      );


    if (videoBlock) {
      videoBlock.insertAdjacentElement(
        'afterend',
        box
      );


      console.log(
        '[q] circle transcript mounted below video'
      );


      return box;
    }


    console.warn(
      '[q] circle block not found; using fallback'
    );


    message.appendChild(
      box
    );


    return box;
  }


  // ============================================================
  // Transcript router
  // ============================================================

  function getTranscriptBox(
    message,
    media,
    button
  ) {
    if (
      media.mediaType ===
      'voice'
    ) {
      return getVoiceTranscriptBox(
        message,
        button
      );
    }


    if (
      media.mediaType ===
      'circle'
    ) {
      return getCircleTranscriptBox(
        message
      );
    }


    throw new Error(
      `Unsupported media type: ${media.mediaType}`
    );
  }


  // ============================================================
  // Shared q click
  // ============================================================

  async function handleQClick(
    event,
    message,
    media,
    button
  ) {
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();


    console.log(
      '[q] clicked',
      {
        id:
          media.id,

        type:
          media.mediaType
      }
    );


    let box;


    try {
      box =
        getTranscriptBox(
          message,
          media,
          button
        );
    } catch (error) {
      console.error(
        '[q] transcript box error',
        error
      );

      return;
    }


    // ----------------------------------------------------------
    // Already loaded -> toggle
    // ----------------------------------------------------------

    if (
      box.dataset.loaded ===
      '1'
    ) {
      box.hidden =
        !box.hidden;

      return;
    }


    // ----------------------------------------------------------
    // Prevent duplicate requests
    // ----------------------------------------------------------

    if (
      button.dataset.qBusy ===
      '1'
    ) {
      return;
    }


    button.dataset.qBusy =
      '1';


    const label =
      button.querySelector(
        '.q-label'
      );


    if (label) {
      label.textContent =
        '…';
    }


    try {
      const result =
        await transcribe(
          media
        );


      box.textContent =
        result.text;


      box.dataset.loaded =
        '1';


      box.hidden =
        false;


      if (label) {
        label.textContent =
          'q';


        label.animate(
          [
            {
              transform:
                'scale(.8)'
            },

            {
              transform:
                'scale(1.15)'
            },

            {
              transform:
                'scale(1)'
            }
          ],
          {
            duration:
              220,

            easing:
              'ease-out'
          }
        );
      }


      console.log(
        '[q] transcription ready',
        {
          id:
            media.id,

          type:
            media.mediaType,

          cached:
            result.cached ??
            false
        }
      );
    } catch (error) {
      console.error(
        '[q] transcription failed',
        media.id,
        error
      );


      if (label) {
        label.textContent =
          '!';


        setTimeout(
          () => {
            label.textContent =
              'q';
          },
          1500
        );
      }
    } finally {
      delete (
        button.dataset.qBusy
      );
    }
  }


  // ============================================================
  // Voice q
  // ============================================================

  function findVoiceButton(
    message
  ) {
    const buttons =
      message.querySelectorAll(
        'button'
      );


    for (
      const button of buttons
    ) {
      if (
        button.classList.contains(
          'q-circle-button'
        )
      ) {
        continue;
      }


      /*
       * If we've already converted it,
       * return our q button.
       */

      if (
        button.dataset.qInstalled ===
        'voice'
      ) {
        return button;
      }


      /*
       * Native Gemspace transcription
       * button contains 16x16 SVG.
       */

      const svg =
        button.querySelector(
          'svg[width="16"][height="16"]'
        );


      if (svg) {
        return button;
      }
    }


    return null;
  }


  function mountVoice(
    message,
    media
  ) {
    const button =
      findVoiceButton(
        message
      );


    if (!button) {
      return;
    }


    // ----------------------------------------------------------
    // Already mounted
    // ----------------------------------------------------------

    if (
      button.dataset.qInstalled ===
      'voice'
    ) {
      const credit =
        createCredit(
          media.id
        );


      positionCredit(
        button,
        credit
      );


      return;
    }


    // ----------------------------------------------------------
    // Convert native transcription button -> q
    // ----------------------------------------------------------

    button.dataset.qInstalled =
      'voice';


    button.innerHTML =
      '<span class="q-label">q</span>';


    button.addEventListener(
      'click',
      (event) => {
        void handleQClick(
          event,
          message,
          media,
          button
        );
      },
      true
    );


    // ----------------------------------------------------------
    // Credit lives in BODY
    // ----------------------------------------------------------

    const credit =
      createCredit(
        media.id
      );


    positionCredit(
      button,
      credit
    );


    console.log(
      '[q] mounted voice',
      media.id
    );
  }


  // ============================================================
  // Circle preview rect
  // ============================================================

  function findCirclePreviewRect(
    message
  ) {
    const videoBlock =
      findCircleVideoBlock(
        message
      );


    if (!videoBlock) {
      return null;
    }


    const candidates = [
      ...videoBlock.querySelectorAll(
        'img, [role="button"]'
      )
    ];


    let bestRect = null;
    let bestArea = 0;


    for (
      const element of candidates
    ) {
      if (
        element.closest(
          '.q-circle-overlay'
        )
      ) {
        continue;
      }


      const rect =
        element.getBoundingClientRect();


      const area =
        rect.width *
        rect.height;


      if (
        rect.width < 150 ||
        rect.height < 150
      ) {
        continue;
      }


      if (
        area >
        bestArea
      ) {
        bestArea =
          area;

        bestRect =
          rect;
      }
    }


    return bestRect;
  }


  // ============================================================
  // Circle button position
  // ============================================================

  function positionCircleButton(
    message,
    overlay
  ) {
    const preview =
      findCirclePreviewRect(
        message
      );


    if (!preview) {
      overlay.hidden =
        true;

      return;
    }


    const messageRect =
      message.getBoundingClientRect();


    overlay.hidden =
      false;


    const right =
      messageRect.right -
      preview.right +
      12;


    const bottom =
      messageRect.bottom -
      preview.bottom +
      12;


    overlay.style.right =
      `${Math.max(
        8,
        right
      )}px`;


    overlay.style.bottom =
      `${Math.max(
        8,
        bottom
      )}px`;
  }


  // ============================================================
  // Circle q
  // ============================================================

  function mountCircle(
    message,
    media
  ) {
    let overlay =
      message.querySelector(
        '.q-circle-overlay'
      );


    let button;


    if (!overlay) {
      overlay =
        document.createElement(
          'div'
        );


      overlay.className =
        'q-circle-overlay';


      overlay.dataset.qFor =
        media.id;


      button =
        document.createElement(
          'button'
        );


      button.type =
        'button';


      button.className =
        'q-circle-button';


      button.dataset.qInstalled =
        'circle';


      button.setAttribute(
        'aria-label',
        'Transcribe video'
      );


      button.title =
        'Transcribe';


      button.innerHTML =
        '<span class="q-label">q</span>';


      button.addEventListener(
        'click',
        (event) => {
          void handleQClick(
            event,
            message,
            media,
            button
          );
        },
        true
      );


      overlay.appendChild(
        button
      );


      /*
       * q button stays attached to the
       * Gemspace message.
       */

      message.appendChild(
        overlay
      );


      console.log(
        '[q] mounted circle',
        media.id
      );
    } else {
      button =
        overlay.querySelector(
          '.q-circle-button'
        );
    }


    positionCircleButton(
      message,
      overlay
    );


    // ----------------------------------------------------------
    // Circle credit ALSO lives in BODY
    // ----------------------------------------------------------

    if (button) {
      const credit =
        createCredit(
          media.id
        );


      positionCredit(
        button,
        credit
      );
    }
  }


  // ============================================================
  // Cleanup floating credits
  // ============================================================

  function cleanupCredits() {
    const credits =
      document.querySelectorAll(
        '.q-credit'
      );


    for (
      const credit of credits
    ) {
      const id =
        credit.dataset.qFor;


      if (!id) {
        credit.remove();
        continue;
      }


      const message =
        document.querySelector(
          `[data-message-id="${CSS.escape(
            id
          )}"]`
        );


      /*
       * Gemspace virtualizes old messages.
       * If message disappears from DOM,
       * don't leave a floating signature.
       */

      if (!message) {
        credit.style.display =
          'none';
      }
    }
  }


  // ============================================================
  // Render
  // ============================================================

  function render() {
    for (
      const [messageId, media]
      of mediaMap
    ) {
      let message;


      try {
        message =
          document.querySelector(
            `[data-message-id="${CSS.escape(
              messageId
            )}"]`
          );
      } catch (error) {
        console.warn(
          '[q] selector failed',
          messageId,
          error
        );

        continue;
      }


      if (!message) {
        const credit =
          document.querySelector(
            `.q-credit[data-q-for="${CSS.escape(
              messageId
            )}"]`
          );


        if (credit) {
          credit.style.display =
            'none';
        }


        continue;
      }


      if (
        media.mediaType ===
        'voice'
      ) {
        mountVoice(
          message,
          media
        );

        continue;
      }


      if (
        media.mediaType ===
        'circle'
      ) {
        mountCircle(
          message,
          media
        );
      }
    }


    cleanupCredits();
  }


  // ============================================================
  // Render scheduler
  // ============================================================

  let renderScheduled =
    false;


  function scheduleRender() {
    if (renderScheduled) {
      return;
    }


    renderScheduled =
      true;


    requestAnimationFrame(
      () => {
        renderScheduled =
          false;


        render();
      }
    );
  }


  // ============================================================
  // MutationObserver
  // ============================================================

  const observer =
    new MutationObserver(
      () => {
        scheduleRender();
      }
    );


  observer.observe(
    document.documentElement,
    {
      childList: true,
      subtree: true
    }
  );


  // ============================================================
  // Scroll
  //
  // IMPORTANT because credit uses position:fixed.
  // ============================================================

  document.addEventListener(
    'scroll',
    scheduleRender,
    {
      passive: true,
      capture: true
    }
  );


  // ============================================================
  // Resize
  // ============================================================

  window.addEventListener(
    'resize',
    scheduleRender,
    {
      passive: true
    }
  );


  // ============================================================
  // Debug API
  // ============================================================

  window.q = {
    media:
      mediaMap,


    render,


    status() {
      console.table(
        [
          ...mediaMap.values()
        ]
      );


      return {
        installed:
          true,

        media:
          mediaMap.size,

        api:
          Q_API
      };
    },


    async health() {
      const response =
        await originalFetch(
          `${Q_API}/health`
        );


      const result =
        await response.json();


      console.log(
        '[q] backend health',
        result
      );


      return result;
    }
  };


  // ============================================================
  // Railway smoke test
  // ============================================================

  try {
    const response =
      await originalFetch(
        `${Q_API}/health`
      );


    const health =
      await response.json();


    console.log(
      '[q] Railway connected',
      health
    );
  } catch (error) {
    console.error(
      '[q] Railway connection failed',
      error
    );
  }


  // ============================================================
  // Ready
  // ============================================================

  console.log(
    '%c q loaded ',
    [
      'background:#111',
      'color:#fff',
      'font-size:16px',
      'font-weight:bold',
      'padding:6px 10px',
      'border-radius:6px'
    ].join(';')
  );


  console.log(
    '[q] API:',
    Q_API
  );


  console.log(
    '[q] signature: ← qwerty was here'
  );


  console.log(
    '[q] signature is mounted OUTSIDE Gemspace message bubbles'
  );


  console.log(
    '[q] waiting for Gemspace media...'
  );


  console.log(
    '[q] switch to another chat and back if media was loaded before q'
  );


  scheduleRender();
})();
      result.catch(fail);
      if (window.q && window.__qInstalled) {
        state.phase='ready';
        alert('q запущен. Если кнопок пока нет, перейдите в другой чат и обратно.');
      }
    } catch { fail(); }
  })();