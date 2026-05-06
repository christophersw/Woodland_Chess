/**
 * Title: engineLines.js — Engine Lines board management and interaction
 * Description:
 *   Manages the Engine Lines board (continuation display) with separate ply sync,
 *   perspective sharing with the main board, and continuation loading from
 *   clickable engine-arrow metadata rendered on the main analysis board.
 *
 * Changelog:
 *   2026-05-05 (#16): Restore Engine Lines controls when a continuation finishes loading
 *   2026-05-05 (#16): Hide Engine Lines controls until a continuation is loaded
 *   2026-05-05 (#16): Synced Engine Lines navigation with the main board and
 *                      clear the continuation when the main board changes independently
 *   2026-05-05 (#16): Added explicit request-state clearing when the continuation partial mounts
 *   2026-05-05 (#16): Replaced fragile DOM rebinding with metadata-driven arrow loading
 *   2026-05-XX: Created for Engine Lines board feature
 */

(function () {
  var ENGINE_LINE_REQUEST_EVENT = 'woodleague:engine-line-requested';
  window.__woodLeagueEngineLineBoardTeardown = null;

  // Local state for Engine Lines board
  var _engineLinesPly = 0;
  var _engineLinesTotal = 0;
  var _engineLinesSubscribers = [];

  // Shared state
  var _currentEngineLineData = null;
  var _syncedMainBoardPly = null;

  /**
   * Return the Engine Lines control elements.
   *
   * @returns {{shell: Element|null, slider: Element|null, plyLabel: Element|null, buttons: Element[]}}
   */
  function _getEngineLineControls() {
    var buttonIds = [
      'engine-lines-btn-start',
      'engine-lines-btn-prev',
      'engine-lines-btn-play',
      'engine-lines-btn-next',
      'engine-lines-btn-end',
      'engine-lines-btn-flip',
    ];
    return {
      shell: document.getElementById('engine-lines-controls'),
      slider: document.getElementById('engine-lines-slider'),
      plyLabel: document.getElementById('engine-lines-ply-label'),
      buttons: buttonIds
        .map(function (id) { return document.getElementById(id); })
        .filter(function (element) { return !!element; }),
    };
  }

  /**
   * Enable or disable the Engine Lines controls as a group.
   *
   * @param {boolean} isEnabled - Whether the controls should be interactive.
   */
  function _setEngineLineControlsEnabled(isEnabled) {
    var controls = _getEngineLineControls();
    if (controls.shell) {
      controls.shell.style.display = isEnabled ? 'flex' : 'none';
    }
    if (controls.slider) {
      controls.slider.disabled = !isEnabled;
      if (!isEnabled) {
        controls.slider.value = 0;
        controls.slider.max = 0;
      }
    }
    if (controls.plyLabel && !isEnabled) {
      controls.plyLabel.textContent = '—';
    }
    controls.buttons.forEach(function (button) {
      button.disabled = !isEnabled;
    });
  }

  function _notifyEngineLines() {
    var state = { ply: _engineLinesPly, totalPlies: _engineLinesTotal };
    for (var i = 0; i < _engineLinesSubscribers.length; i++) {
      try { _engineLinesSubscribers[i](state); } catch (e) { /* ignore */ }
    }
  }

  /**
   * Return the shared Engine Lines DOM elements.
   *
   * @returns {{container: Element|null, header: Element|null, loading: Element|null}}
   */
  function _getEngineLineElements() {
    return {
      container: document.getElementById('engine-lines-container'),
      header: document.getElementById('engine-lines-header'),
      loading: document.getElementById('engine-lines-loading'),
    };
  }

  /**
   * Apply the current loading or error state to the Engine Lines panel.
   *
   * @param {boolean} isLoading - Whether a continuation request is in flight.
   * @param {string} errorMessage - Optional error message to render in the panel.
   */
  function _setEngineLineRequestState(isLoading, errorMessage) {
    var elements = _getEngineLineElements();
    if (!elements.container) {
      return;
    }

    if (elements.loading) {
      elements.loading.style.display = isLoading ? 'block' : 'none';
    }
    elements.container.style.opacity = isLoading ? '0.5' : '1';

    if (!isLoading && errorMessage) {
      var errorDiv = document.createElement('div');
      errorDiv.style.color = '#B53541';
      errorDiv.style.fontSize = '.72rem';
      errorDiv.textContent = errorMessage;
      elements.container.innerHTML = '';
      elements.container.appendChild(errorDiv);
    }
  }

  /**
   * Check whether the given HTMX event is targeting the Engine Lines container.
   *
   * @param {Event} evt - HTMX lifecycle event.
   * @returns {boolean}
   */
  function _isEngineLinesRequest(evt) {
    return !!(evt && evt.detail && evt.detail.target && evt.detail.target.id === 'engine-lines-container');
  }

  /**
   * Load the requested continuation from an arrow-selection payload.
   *
   * @param {{ply: number, moveUci: string, engine: string, tier: number, deltaText: string}} arrowData
   */
  function _loadArrowSelection(arrowData) {
    var slug = window.ANALYSIS_DATA && window.ANALYSIS_DATA.slug ? window.ANALYSIS_DATA.slug : '';
    if (!slug || !arrowData || !arrowData.moveUci) {
      return;
    }

    window.WoodLeagueEngineLines.loadEngineLine(
      slug,
      parseInt(arrowData.ply, 10) || 0,
      arrowData.moveUci,
      arrowData.engine || 'sf',
      parseInt(arrowData.tier, 10) || 1,
      arrowData.deltaText || ''
    );
  }

  /**
   * Sync the main board ply to the current Engine Lines ply.
   */
  function _syncMainBoardPlyFromEngineLine() {
    if (!_currentEngineLineData || !window.WoodLeagueAnalysis) {
      return;
    }

    var targetPly = _currentEngineLineData.baseMainLinePly + _engineLinesPly;
    _syncedMainBoardPly = targetPly;
    window.WoodLeagueAnalysis.setPly(targetPly);
  }

  /**
   * Clear the current Engine Lines board selection and reset its UI.
   */
  function _clearEngineLineBoard() {
    var elements = _getEngineLineElements();

    _currentEngineLineData = null;
    _engineLinesPly = 0;
    _engineLinesTotal = 0;
    _syncedMainBoardPly = null;

    if (elements.loading) {
      elements.loading.style.display = 'none';
    }
    if (elements.container) {
      elements.container.style.opacity = '1';
      elements.container.innerHTML = '';
    }
    if (elements.header) {
      elements.header.textContent = 'Click engine arrow to explore';
    }

    _setEngineLineControlsEnabled(false);
    _notifyEngineLines();
  }

  window.WoodLeagueEngineLines = {
    /**
     * Set the Engine Lines board ply. Clamps to [0, totalPlies], notifies subscribers.
     */
    setPly: function (ply) {
      _engineLinesPly = Math.max(0, Math.min(_engineLinesTotal, parseInt(ply, 10) || 0));
      _notifyEngineLines();
      _syncMainBoardPlyFromEngineLine();
    },

    /**
     * Set total plies for Engine Lines board (called when continuation is loaded).
     */
    setTotalPlies: function (total) {
      _engineLinesTotal = Math.max(0, parseInt(total, 10) || 0);
      _engineLinesPly = Math.min(_engineLinesPly, _engineLinesTotal);
      _setEngineLineControlsEnabled(_currentEngineLineData !== null);
      _notifyEngineLines();
    },

    /**
     * Subscribe to Engine Lines state changes.
     */
    subscribe: function (fn) {
      _engineLinesSubscribers.push(fn);
      return function () {
        _engineLinesSubscribers = _engineLinesSubscribers.filter(function (s) { return s !== fn; });
      };
    },

    /**
     * Get current Engine Lines state.
     */
    getState: function () {
      return { ply: _engineLinesPly, totalPlies: _engineLinesTotal };
    },

    /**
     * Load an engine line continuation from the server.
     * Called when user clicks an arrow on the main board.
     */
    loadEngineLine: function (slug, ply, moveUCI, engine, tier, deltaText) {
      var perspective = window.WoodLeagueAnalysis ? window.WoodLeagueAnalysis.getState().perspective : 'white';
      var elements = _getEngineLineElements();

      if (!elements.container) return;

      // Reset ply when loading new line
      _engineLinesPly = 0;
      _currentEngineLineData = {
        slug: slug,
        ply: ply,
        uci: moveUCI,
        engine: engine,
        tier: tier,
        deltaText: deltaText || '',
        baseMainLinePly: parseInt(ply, 10) + 1,
      };

      _setEngineLineRequestState(true, '');

      var url = '/_partials/games/' + slug + '/engine-line/?ply=' + ply +
                 '&move_uci=' + encodeURIComponent(moveUCI) +
                 '&engine=' + encodeURIComponent(engine) +
                 '&tier=' + encodeURIComponent(tier) +
                 '&delta_label=' + encodeURIComponent(deltaText || '') +
                 '&orientation=' + encodeURIComponent(perspective);

      if (typeof htmx === 'undefined') {
        _setEngineLineRequestState(false, 'HTMX unavailable');
        return;
      }

      htmx.ajax('GET', url, {
        target: '#engine-lines-container',
        swap: 'innerHTML',
      });
    },

    /**
     * Open a continuation from the main-board arrow metadata payload.
     *
      * @param {{ply: number, moveUci: string, engine: string, tier: number, deltaText: string}} arrowData
      */
    openArrowLine: function (arrowData) {
      _loadArrowSelection(arrowData);
    },

    /**
     * Clear the loading state after a continuation partial has mounted.
     */
    clearRequestState: function () {
      _setEngineLineRequestState(false, '');
    },

    /**
     * Clear the current continuation and reset the Engine Lines panel.
     */
    clearBoard: function () {
      _clearEngineLineBoard();
    },
  };

  document.addEventListener(ENGINE_LINE_REQUEST_EVENT, function (evt) {
    _loadArrowSelection(evt.detail || {});
  });

  if (typeof htmx !== 'undefined') {
    document.body.addEventListener('htmx:afterSwap', function (evt) {
      if (_isEngineLinesRequest(evt)) {
        _setEngineLineRequestState(false, '');
      }
    });

    document.body.addEventListener('htmx:responseError', function (evt) {
      if (_isEngineLinesRequest(evt)) {
        _setEngineLineRequestState(false, 'Failed to load engine line');
      }
    });

    document.body.addEventListener('htmx:sendError', function (evt) {
      if (_isEngineLinesRequest(evt)) {
        _setEngineLineRequestState(false, 'Failed to load engine line');
      }
    });
  }

  /**
   * Mirror perspective from main board to Engine Lines board.
   */
  if (window.WoodLeagueAnalysis) {
    var previousMainBoardState = window.WoodLeagueAnalysis.getState();
    var mainUnsubscribe = window.WoodLeagueAnalysis.subscribe(function (state) {
      if (_currentEngineLineData && state.ply !== previousMainBoardState.ply) {
        if (_syncedMainBoardPly !== null && state.ply === _syncedMainBoardPly) {
          _syncedMainBoardPly = null;
        } else {
          _clearEngineLineBoard();
        }
      }

      // When only the perspective changes, keep the current continuation in sync.
      if (_currentEngineLineData && state.perspective !== previousMainBoardState.perspective) {
        var currentEngineLinePly = window.WoodLeagueEngineLines.getState().ply;
        var arrowData = _currentEngineLineData;
        window.WoodLeagueEngineLines.loadEngineLine(
          arrowData.slug,
          arrowData.ply,
          arrowData.uci,
          arrowData.engine,
          arrowData.tier,
          arrowData.deltaText || ''
        );
        _engineLinesPly = currentEngineLinePly;
      }

      previousMainBoardState = {
        ply: state.ply,
        perspective: state.perspective,
        totalPlies: state.totalPlies,
      };
    });
  }

  _setEngineLineControlsEnabled(false);
})();

/**
 * Setup Engine Lines board controls when an engine line board is rendered.
 * This is called from within the engine-line partial template.
 */
window.setupEngineLineBoard = function (framesJson, arrowLabelsJson, sanListJson, totalFrames) {
  var frames = JSON.parse(framesJson || '[]');
  var totalFrames = frames.length;

  if (window.__woodLeagueEngineLineBoardTeardown) {
    window.__woodLeagueEngineLineBoardTeardown();
    window.__woodLeagueEngineLineBoardTeardown = null;
  }

  var boardRoot = document.getElementById('engine-line-board-inner');
  var container = document.getElementById('engine-line-board-svg-wrap');
  var slider = document.getElementById('engine-lines-slider');
  var plyLabel = document.getElementById('engine-lines-ply-label');
  var btnStart = document.getElementById('engine-lines-btn-start');
  var btnPrev = document.getElementById('engine-lines-btn-prev');
  var btnPlay = document.getElementById('engine-lines-btn-play');
  var btnNext = document.getElementById('engine-lines-btn-next');
  var btnEnd = document.getElementById('engine-lines-btn-end');
  var btnFlip = document.getElementById('engine-lines-btn-flip');

  if (!container || !boardRoot) return;

  var playing = false;
  var playTimer = null;

  // Inform EngineLines of total ply count
  window.WoodLeagueEngineLines.setTotalPlies(totalFrames - 1);

  function renderPly(ply) {
    ply = Math.max(0, Math.min(totalFrames - 1, ply));
    if (frames[ply]) {
      container.innerHTML = frames[ply];
    }
    slider.value = ply;
    if (ply === 0) {
      plyLabel.textContent = '+0 (start)';
    } else {
      var moveNum = Math.ceil(ply / 2);
      var dots = ply % 2 === 0 ? '...' : '.';
      plyLabel.textContent = '+' + ply + ' (' + moveNum + dots + ')';
    }
  }

  // Subscribe to EngineLines state changes
  var unsubscribe = window.WoodLeagueEngineLines.subscribe(function (state) {
    renderPly(state.ply);
  });

  // Render initial state
  renderPly(0);

  // Control button handlers
  btnStart.onclick = function () {
    window.WoodLeagueEngineLines.setPly(0);
  };

  btnPrev.onclick = function () {
    var cur = window.WoodLeagueEngineLines.getState().ply;
    window.WoodLeagueEngineLines.setPly(cur - 1);
  };

  btnNext.onclick = function () {
    var cur = window.WoodLeagueEngineLines.getState().ply;
    window.WoodLeagueEngineLines.setPly(cur + 1);
  };

  btnEnd.onclick = function () {
    window.WoodLeagueEngineLines.setPly(totalFrames - 1);
  };

  btnFlip.onclick = function () {
    var mainState = window.WoodLeagueAnalysis ? window.WoodLeagueAnalysis.getState() : {};
    var nextPerspective = mainState.perspective === 'white' ? 'black' : 'white';
    if (window.WoodLeagueAnalysis) {
      window.WoodLeagueAnalysis.setPerspective(nextPerspective);
    }
    // The perspective change will trigger a reload of the engine line board
  };

  btnPlay.onclick = function () {
    if (playing) {
      clearInterval(playTimer);
      playing = false;
      btnPlay.innerHTML = '&#x25B6;';
    } else {
      var cur = window.WoodLeagueEngineLines.getState().ply;
      if (cur >= totalFrames - 1) cur = 0;
      playing = true;
      btnPlay.innerHTML = '&#x23F8;';
      playTimer = setInterval(function () {
        var state = window.WoodLeagueEngineLines.getState();
        if (state.ply >= totalFrames - 1) {
          clearInterval(playTimer);
          playing = false;
          btnPlay.innerHTML = '&#x25B6;';
          return;
        }
        window.WoodLeagueEngineLines.setPly(state.ply + 1);
      }, 800);
    }
  };

  slider.oninput = function () {
    window.WoodLeagueEngineLines.setPly(parseInt(this.value));
  };

  // Enable slider and controls
  slider.disabled = false;
  slider.max = totalFrames - 1;
  btnStart.disabled = false;
  btnPrev.disabled = false;
  btnPlay.disabled = false;
  btnNext.disabled = false;
  btnEnd.disabled = false;
  btnFlip.disabled = false;

  window.__woodLeagueEngineLineBoardTeardown = function () {
    if (unsubscribe) unsubscribe();
    if (playTimer) clearInterval(playTimer);
  };

  // Clean up subscription when Engine Lines board is replaced
  boardRoot.addEventListener('htmx:beforeCleanupElement', window.__woodLeagueEngineLineBoardTeardown, { once: true });
};
