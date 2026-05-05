/**
 * Title: engineLines.js — Engine Lines board management and interaction
 * Description:
 *   Manages the Engine Lines board (continuation display) with separate ply sync,
 *   perspective sharing with main board, and arrow click handlers for loading continuations.
 *
 * Changelog:
 *   2026-05-XX: Created for Engine Lines board feature
 */

(function () {
  // Local state for Engine Lines board
  var _engineLinesPly = 0;
  var _engineLinesTotal = 0;
  var _engineLinesSubscribers = [];

  // Shared state
  var _currentEngineLineData = null;

  function _notifyEngineLines() {
    var state = { ply: _engineLinesPly, totalPlies: _engineLinesTotal };
    for (var i = 0; i < _engineLinesSubscribers.length; i++) {
      try { _engineLinesSubscribers[i](state); } catch (e) { /* ignore */ }
    }
  }

  window.WoodLeagueEngineLines = {
    /**
     * Set the Engine Lines board ply. Clamps to [0, totalPlies], notifies subscribers.
     */
    setPly: function (ply) {
      _engineLinesPly = Math.max(0, Math.min(_engineLinesTotal, parseInt(ply, 10) || 0));
      _notifyEngineLines();
    },

    /**
     * Set total plies for Engine Lines board (called when continuation is loaded).
     */
    setTotalPlies: function (total) {
      _engineLinesTotal = Math.max(0, parseInt(total, 10) || 0);
      _engineLinesPly = Math.min(_engineLinesPly, _engineLinesTotal);
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
    loadEngineLine: function (slug, ply, moveUCI, engine, tier) {
      var container = document.getElementById('engine-lines-container');
      var header = document.getElementById('engine-lines-header');
      var loading = document.getElementById('engine-lines-loading');
      var perspective = window.WoodLeagueAnalysis ? window.WoodLeagueAnalysis.getState().perspective : 'white';

      if (!container) return;

      loading.style.display = 'block';
      container.style.opacity = '0.5';

      // Reset ply when loading new line
      _engineLinesPly = 0;

      var url = '/_partials/games/' + slug + '/engine-line/?ply=' + ply +
                '&move_uci=' + encodeURIComponent(moveUCI) +
                '&engine=' + encodeURIComponent(engine) +
                '&tier=' + encodeURIComponent(tier) +
                '&orientation=' + encodeURIComponent(perspective);

      if (typeof htmx !== 'undefined') {
        htmx.ajax('GET', url, {
          target: '#engine-lines-container',
          swap: 'innerHTML',
          onBeforeSwap: function () {
            loading.style.display = 'none';
            container.style.opacity = '1';
          },
          onError: function () {
            loading.style.display = 'none';
            container.style.opacity = '1';
            // Use textContent to avoid XSS
            var errorDiv = document.createElement('div');
            errorDiv.style.color = '#B53541';
            errorDiv.style.fontSize = '.72rem';
            errorDiv.textContent = 'Failed to load engine line';
            container.innerHTML = '';
            container.appendChild(errorDiv);
          }
        });
      }
    },
  };

  /**
   * Initialize arrow click handlers on the main board.
   * Called after main board is loaded.
   */
  window.initializeEngineLineArrowHandlers = function () {
    var boardSvgWrap = document.getElementById('board-svg-wrap');
    if (!boardSvgWrap) return;

    // Remove existing listeners if any
    var arrowElements = boardSvgWrap.querySelectorAll('line[data-arrow-index], polygon[data-arrow-index]');
    arrowElements.forEach(function (el) {
      // Create a new element to remove all listeners
      var newEl = el.cloneNode(true);
      el.parentNode.replaceChild(newEl, el);
    });

    // Re-query after cloning
    arrowElements = boardSvgWrap.querySelectorAll('line[data-arrow-index], polygon[data-arrow-index]');
    
    arrowElements.forEach(function (el) {
      el.style.cursor = 'pointer';
      
      el.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();

        // Extract arrow metadata from the element
        var arrowIndex = el.getAttribute('data-arrow-index');
        if (arrowIndex === null) return;

        // Get arrow labels to find engine, move, and tier
        var arrowLabelsEl = document.getElementById('board-arrows-json');
        if (!arrowLabelsEl) return;

        try {
          var arrowLabels = JSON.parse(arrowLabelsEl.textContent);
          var currentPly = window.WoodLeagueAnalysis ? window.WoodLeagueAnalysis.getState().ply : 0;

          var labelForPly = arrowLabels[currentPly];
          if (!labelForPly || !labelForPly[arrowIndex]) return;

          var arrowData = labelForPly[arrowIndex];
          var engine = arrowData.engine || 'sf';
          var uci = arrowData.uci || '';
          
          // Determine tier based on arrow index (0=tier1, 1=tier2, 2=tier3)
          var tier = parseInt(arrowIndex) + 1;
          if (tier > 3) tier = 3;

          if (!uci) return;

          var slug = window.ANALYSIS_DATA && window.ANALYSIS_DATA.slug ? 
                     window.ANALYSIS_DATA.slug : null;
          if (!slug) return;

          // Load the engine line continuation
          window.WoodLeagueEngineLines.loadEngineLine(slug, currentPly, uci, engine, tier);
        } catch (e) {
          console.error('Error loading engine line:', e);
        }
      });

      // Add hover feedback
      el.addEventListener('mouseenter', function () {
        el.style.opacity = '0.8';
        el.style.filter = 'brightness(1.2)';
      });

      el.addEventListener('mouseleave', function () {
        el.style.opacity = '';
        el.style.filter = '';
      });
    });
  };

  /**
   * Handle board partial updates to re-attach arrow handlers.
   */
  document.addEventListener('htmx:afterSettle', function (evt) {
    if (evt.detail && evt.detail.target && evt.detail.target.id === 'board-container') {
      // Main board was updated, re-initialize arrow handlers
      setTimeout(window.initializeEngineLineArrowHandlers, 50);
    }
  });

  /**
   * Also initialize on page load.
   */
  document.addEventListener('DOMContentLoaded', function () {
    setTimeout(window.initializeEngineLineArrowHandlers, 100);
  });

  /**
   * Mirror perspective from main board to Engine Lines board.
   */
  if (window.WoodLeagueAnalysis) {
    var mainUnsubscribe = window.WoodLeagueAnalysis.subscribe(function (state) {
      // When perspective changes on main board, reload engine lines board with new perspective
      var currentEngineLinePly = window.WoodLeagueEngineLines.getState().ply;
      if (_currentEngineLineData && currentEngineLinePly === 0) {
        // Only reload if showing initial ply (user hasn't navigated within continuation)
        var container = document.getElementById('engine-lines-container');
        if (container && container.querySelector('[data-engine-line]')) {
          // Re-render with new perspective would happen here if needed
          // For now, we'll reload the continuation with new perspective
          var arrowData = _currentEngineLineData;
          if (arrowData) {
            window.WoodLeagueEngineLines.loadEngineLine(
              arrowData.slug, 
              arrowData.ply, 
              arrowData.uci, 
              arrowData.engine, 
              arrowData.tier
            );
          }
        }
      }
    });
  }
})();

/**
 * Setup Engine Lines board controls when an engine line board is rendered.
 * This is called from within the engine-line partial template.
 */
window.setupEngineLineBoard = function (framesJson, arrowLabelsJson, sanListJson, totalFrames) {
  var frames = JSON.parse(framesJson || '[]');
  var totalFrames = frames.length;

  var container = document.getElementById('engine-lines-container');
  var slider = document.getElementById('engine-lines-slider');
  var plyLabel = document.getElementById('engine-lines-ply-label');
  var btnStart = document.getElementById('engine-lines-btn-start');
  var btnPrev = document.getElementById('engine-lines-btn-prev');
  var btnPlay = document.getElementById('engine-lines-btn-play');
  var btnNext = document.getElementById('engine-lines-btn-next');
  var btnEnd = document.getElementById('engine-lines-btn-end');
  var btnFlip = document.getElementById('engine-lines-btn-flip');

  if (!container) return;

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

  // Clean up subscription when Engine Lines board is replaced
  container.addEventListener('htmx:beforeCleanupElement', function () {
    if (unsubscribe) unsubscribe();
    if (playTimer) clearInterval(playTimer);
  });
};
