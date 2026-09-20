(function () {
  "use strict";
  var DATA = window.UGRP_DATA;
  var COURSES = DATA.courses;
  var PREREQ = DATA.prereqMap;
  var REVERSE = DATA.reverseMap;
  var SYNERGY = DATA.synergy;
  var DEPT_NAMES = DATA.deptNames;

  var COURSE_BY_CODE = {};
  COURSES.forEach(function (c) { COURSE_BY_CODE[c.code] = c; });

  // ---- synergy lookup index (undirected) ----
  var SYNERGY_INDEX = {};
  SYNERGY.forEach(function (s) {
    (SYNERGY_INDEX[s.a] = SYNERGY_INDEX[s.a] || []).push({ code: s.b, conf: s.conf });
    (SYNERGY_INDEX[s.b] = SYNERGY_INDEX[s.b] || []).push({ code: s.a, conf: s.conf });
  });

  function resolveCourse(codeStr) {
    if (COURSE_BY_CODE[codeStr]) return COURSE_BY_CODE[codeStr];
    var m = codeStr.match(/[A-Z]+\d+/);
    if (m && COURSE_BY_CODE[m[0]]) return COURSE_BY_CODE[m[0]];
    return null;
  }

  function deptOf(codeStr) {
    var m = codeStr.match(/^[A-Za-z]+/);
    return m ? m[0] : "?";
  }

  function deptLabel(prefix) {
    return DEPT_NAMES[prefix] ? DEPT_NAMES[prefix] + " (" + prefix + ")" : prefix;
  }

  // ---- lightweight text similarity engine: char-bigram + word-token cosine ----
  function normalize(s) {
    return (s || "").toLowerCase().replace(/[^\p{L}\p{N}\s]/gu, " ").replace(/\s+/g, " ").trim();
  }

  function charBigrams(s) {
    var t = s.replace(/\s+/g, "");
    var map = Object.create(null);
    for (var i = 0; i < t.length - 1; i++) {
      var g = t.substr(i, 2);
      map[g] = (map[g] || 0) + 1;
    }
    return map;
  }

  function wordTokens(s) {
    var map = Object.create(null);
    s.split(" ").forEach(function (w) {
      if (w.length >= 2) map[w] = (map[w] || 0) + 1;
    });
    return map;
  }

  function vecNorm(map) {
    var sum = 0;
    for (var k in map) sum += map[k] * map[k];
    return Math.sqrt(sum);
  }

  function cosine(a, aNorm, b, bNorm) {
    if (!aNorm || !bNorm) return 0;
    var dot = 0;
    var small = Object.keys(a).length < Object.keys(b).length ? a : b;
    var other = small === a ? b : a;
    for (var k in small) {
      if (other[k]) dot += small[k] * other[k];
    }
    return dot / (aNorm * bNorm);
  }

  // IDF over the real course corpus: down-weights generic terms ("연구", "학과", "이론" …)
  // so distinctive domain terms ("로봇", "반도체", "통신" …) dominate the match — a cheap
  // stand-in for the embedding fine-tuning planned in the roadmap (BGE-m3, axis A).
  function buildIdf(termMaps) {
    var df = Object.create(null);
    termMaps.forEach(function (m) {
      for (var k in m) df[k] = (df[k] || 0) + 1;
    });
    var idf = Object.create(null);
    var n = termMaps.length;
    for (var k in df) idf[k] = Math.log((n + 1) / (df[k] + 1)) + 1;
    return idf;
  }

  function applyIdf(map, idf) {
    var out = Object.create(null);
    for (var k in map) out[k] = map[k] * (idf[k] || 1);
    return out;
  }

  // precompute per-course raw term vectors, then corpus-wide IDF, then weighted vectors
  var rawBi = [], rawWd = [];
  COURSES.forEach(function (c) {
    var norm = normalize(c.corpus || (c.kr + " " + c.desc));
    var bi = charBigrams(norm);
    var wd = wordTokens(norm);
    c._rawBi = bi; c._rawWd = wd;
    rawBi.push(bi); rawWd.push(wd);
  });
  var BI_IDF = buildIdf(rawBi);
  var WD_IDF = buildIdf(rawWd);
  COURSES.forEach(function (c) {
    c._bi = applyIdf(c._rawBi, BI_IDF);
    c._biNorm = vecNorm(c._bi);
    c._wd = applyIdf(c._rawWd, WD_IDF);
    c._wdNorm = vecNorm(c._wd);
  });

  function search(query) {
    var norm = normalize(query);
    var qBi = applyIdf(charBigrams(norm), BI_IDF);
    var qBiNorm = vecNorm(qBi);
    var qWd = applyIdf(wordTokens(norm), WD_IDF);
    var qWdNorm = vecNorm(qWd);

    var results = COURSES.map(function (c) {
      var biSim = cosine(qBi, qBiNorm, c._bi, c._biNorm);
      var wdSim = cosine(qWd, qWdNorm, c._wd, c._wdNorm);
      var nameHit = c.kr && norm.indexOf(normalize(c.kr)) === -1 && normalize(c.kr).length > 1 &&
        norm.split(" ").some(function (w) { return w.length >= 2 && c.kr.indexOf(w) !== -1; }) ? 0.05 : 0;
      // char-bigram channel weighted highest: it tolerates Korean particle/inflection
      // variation (로봇이/로봇을/로봇제어) that exact word-token matching misses, and is
      // less thrown off by a single rare acronym token (e.g. "AI") than the word channel.
      var score = biSim * 0.8 + wdSim * 0.15 + nameHit;
      return { course: c, score: score };
    });
    results.sort(function (a, b) { return b.score - a.score; });
    return results.slice(0, 5).filter(function (r) { return r.score > 0.01; });
  }

  // ---- prerequisite chain (backward) & unlocks (forward), real graph walk ----
  function buildChain(code, depth) {
    var seen = {};
    var levels = [];
    var frontier = [code];
    seen[code] = true;
    for (var d = 0; d < depth && frontier.length; d++) {
      var next = [];
      var levelItems = [];
      frontier.forEach(function (c) {
        var prereqs = PREREQ[c] || [];
        prereqs.forEach(function (p) {
          if (!seen[p]) {
            seen[p] = true;
            next.push(p);
            levelItems.push(p);
          }
        });
      });
      if (levelItems.length) levels.push(levelItems);
      frontier = next;
    }
    levels.reverse(); // earliest prerequisites first
    return levels; // array of levels (each an array of course-code strings)
  }

  function getUnlocks(code) {
    return (REVERSE[code] || []).slice(0, 4);
  }

  function crossDeptSynergies(code) {
    var focusDept = deptOf(code);
    var links = SYNERGY_INDEX[code] || [];
    return links.filter(function (l) {
      return deptOf(l.code) !== focusDept;
    }).sort(function (a, b) { return b.conf - a.conf; });
  }

  // ---- rendering ----
  var $ = function (id) { return document.getElementById(id); };

  function renderResults(results, query) {
    var list = $("resultList");
    list.innerHTML = "";
    if (!results.length) {
      list.innerHTML = '<p class="empty-note">일치하는 교과목을 찾지 못했습니다. 다른 표현으로 다시 시도해보세요 (예: "로봇", "인공지능", "신소재", "반도체 소자").</p>';
      $("focusArea").style.display = "none";
      return;
    }
    results.forEach(function (r, i) {
      var pct = Math.min(99, Math.round(r.score * 140));
      var card = document.createElement("div");
      card.className = "match-card" + (i === 0 ? " is-top" : "");
      card.innerHTML =
        '<div class="match-top">' +
          '<div class="match-topic">' + r.course.kr +
            '<span class="en">' + r.course.code + " · " + deptLabel(r.course.dept) + '</span>' +
          '</div>' +
          '<div class="score-badge">유사도 ' + pct + '%</div>' +
        '</div>' +
        '<div class="score-bar-track"><div class="score-bar-fill" style="width:' + pct + '%"></div></div>' +
        '<p class="match-desc">' + (r.course.desc || "설명 없음") + '</p>' +
        '<button class="focus-btn" type="button" data-code="' + r.course.code + '">이 과목 기준 경로 보기 →</button>';
      list.appendChild(card);
    });

    Array.prototype.forEach.call(list.querySelectorAll(".focus-btn"), function (btn) {
      btn.addEventListener("click", function () {
        renderFocus(btn.getAttribute("data-code"));
      });
    });

    renderFocus(results[0].course.code);
  }

  function renderFocus(code) {
    var course = COURSE_BY_CODE[code];
    if (!course) return;
    $("focusArea").style.display = "";
    $("focusTitle").textContent = course.kr + " (" + course.code + ")";

    // stage 2: prerequisite chain
    var chain = buildChain(code, 3);
    var pathEl = $("pathDiagram");
    pathEl.innerHTML = "";
    if (!chain.length) {
      pathEl.innerHTML = '<p class="empty-note">등록된 선수과목 데이터가 없는 과목입니다 (입문 과목이거나 데이터 미수집).</p>';
    } else {
      var focusDept = deptOf(code);
      chain.forEach(function (level, li) {
        var row = document.createElement("div");
        row.className = "path-diagram";
        level.forEach(function (codeStr, i) {
          if (i > 0) {
            var arrow = document.createElement("span");
            arrow.className = "path-arrow";
            arrow.textContent = "+";
            row.appendChild(arrow);
          }
          var c = resolveCourse(codeStr);
          var crossDept = c && deptOf(c.code) !== focusDept;
          var node = document.createElement("span");
          node.className = "path-node" + (crossDept ? " cross" : "");
          node.textContent = (c ? c.kr + " " : "") + codeStr;
          row.appendChild(node);
        });
        var arrowDown = document.createElement("span");
        arrowDown.className = "path-arrow";
        arrowDown.textContent = "→";
        row.appendChild(arrowDown);
        pathEl.appendChild(row);
      });
      var final = document.createElement("div");
      final.className = "path-diagram";
      var tip = document.createElement("span");
      tip.className = "path-node tip";
      tip.textContent = course.kr + " " + course.code;
      final.appendChild(tip);
      pathEl.appendChild(final);
    }

    // unlocks (forward)
    var unlocks = getUnlocks(code);
    var unlockEl = $("unlockList");
    unlockEl.innerHTML = "";
    if (unlocks.length) {
      unlocks.forEach(function (u) {
        var c = COURSE_BY_CODE[u];
        var item = document.createElement("span");
        item.className = "kw-chip";
        item.textContent = (c ? c.kr : u) + " · " + u;
        unlockEl.appendChild(item);
      });
      $("unlockWrap").style.display = "";
    } else {
      $("unlockWrap").style.display = "none";
    }

    // stage 3: cross-department fusion signal (real hasSynergyWith data)
    var cross = crossDeptSynergies(code);
    var fusionEl = $("fusionBanner");
    if (cross.length) {
      var top = cross[0];
      var tc = resolveCourse(top.code);
      fusionEl.innerHTML = '<div class="fusion-banner">⇄ <code>' + code + '</code>(' + deptLabel(deptOf(code)) +
        ') 과목이 <code>' + top.code + '</code>' + (tc ? " " + tc.kr : "") + '(' + deptLabel(deptOf(top.code)) +
        ') 과 실제 hasSynergyWith 관계로 연결되어 있습니다 (신뢰도 ' + top.conf.toFixed(1) + ') — 타과 융합 신호 (MVP #4)</div>';
    } else {
      fusionEl.innerHTML = '<div class="fusion-banner muted">이 과목은 현재 데이터에서 타과 융합(hasSynergyWith) 신호가 발견되지 않았습니다.</div>';
    }

    // stage 4: template-based explanation, built from real computed values (not LLM)
    var chainCodes = chain.length ? chain[chain.length - 1] : [];
    var chainNames = chainCodes.map(function (c) {
      var r = resolveCourse(c);
      return r ? r.kr : c;
    });
    var explainEl = $("explainText");
    var p1 = '입력하신 관심사는 <mark>' + course.kr + ' (' + course.code + ')</mark> 교과목과 텍스트 유사도가 가장 높게 계산되었습니다 — ' +
      deptLabel(course.dept) + ' 소속 실제 커리큘럼북 데이터 기준입니다.';
    var p2 = chainCodes.length
      ? '선수과목 그래프를 역추적하면 <code>' + chainNames.join(', ') + '</code> 과목에서 시작해 <code>' + course.code + '</code>로 이어지는 실제 이수 경로가 도출됩니다.'
      : '이 과목은 그래프상 최상위(입문) 노드로, 별도 선수과목 없이 바로 시작할 수 있습니다.';
    var p3 = cross.length
      ? '동시에 <code>' + cross[0].code + '</code> 과목과의 실제 hasSynergyWith 관계로 인해 ' + deptLabel(deptOf(cross[0].code)) + ' 쪽 타과 융합 경로도 함께 고려할 수 있습니다.'
      : '연구실 매칭 데이터는 아직 파이프라인 구축 전 단계로, 로드맵 1개월차 작업(연구실 키워드 크롤링)이 완료되면 이 설명에 실제 연구실 근거가 추가될 예정입니다.';
    explainEl.innerHTML = "<p>" + p1 + "</p><p>" + p2 + "</p><p>" + p3 + "</p>";
  }

  function run(query) {
    if (!query || !query.trim()) return;
    $("inputEcho").textContent = query;
    var results = search(query);
    renderResults(results, query);
  }

  // ---- wire up UI ----
  var input = $("queryInput");
  var goBtn = $("goBtn");
  goBtn.addEventListener("click", function () { run(input.value); });
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") run(input.value);
  });

  Array.prototype.forEach.call(document.querySelectorAll(".query-chip"), function (chip) {
    chip.addEventListener("click", function () {
      input.value = chip.textContent;
      run(chip.textContent);
    });
  });

  $("statCourses").textContent = COURSES.length;
  $("statPrereq").textContent = Object.keys(PREREQ).length;
  $("statSynergy").textContent = SYNERGY.length;

  run("피지컬 AI 시대에서 로봇이 안전하게 작동하는 것을 연구하고 싶어요");
})();
