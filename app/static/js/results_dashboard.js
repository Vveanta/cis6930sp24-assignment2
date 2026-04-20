/* global Plotly, L */
(function () {
  const raw = document.getElementById("results-json-raw");
  const locRaw = document.getElementById("locations-json-raw");
  if (!raw) return;

  const fullData = JSON.parse(raw.textContent);
  const locationsFallback = locRaw ? JSON.parse(locRaw.textContent) : [];

  function parseIncidentTime(row) {
    const t = row["Incident Time"];
    if (!t || String(t).trim() === "") return null;
    const d = new Date(t);
    return isNaN(d.getTime()) ? null : d;
  }

  function filterByRange(rows, start, end) {
    if (!start && !end) return rows;
    const s = start ? new Date(start + "T00:00:00") : null;
    const e = end ? new Date(end + "T23:59:59") : null;
    return rows.filter((row) => {
      const dt = parseIncidentTime(row);
      if (!dt) return true;
      if (s && dt < s) return false;
      if (e && dt > e) return false;
      return true;
    });
  }

  function splitCompare(rows, a0, a1, b0, b1) {
    const A = filterByRange(rows, a0, a1);
    const B = filterByRange(rows, b0, b1);
    return { A, B };
  }

  function aggregateData(rows, key) {
    const counts = {};
    rows.forEach((item) => {
      const k = item[key];
      counts[k] = (counts[k] || 0) + 1;
    });
    return Object.keys(counts).map((k) => ({ key: k, count: counts[k] }));
  }

  const daysOfWeekLabels = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

  function ensureAllDays(data) {
    const dayCounts = {};
    daysOfWeekLabels.forEach((_, index) => {
      dayCounts[index + 1] = 0;
    });
    data.forEach((item) => {
      dayCounts[item.key] = item.count;
    });
    return Object.keys(dayCounts).map((k) => ({ key: k, count: dayCounts[k] }));
  }

  function aggregateAndSortDataByKey(rows, key, topN) {
    const counts = {};
    rows.forEach((item) => {
      counts[item[key]] = (counts[item[key]] || 0) + 1;
    });
    return Object.keys(counts)
      .map((k) => ({ key: k, count: counts[k] }))
      .sort((a, b) => b.count - a.count)
      .slice(0, topN);
  }

  function aggregateEMSSTAT(rows) {
    const counts = { true: 0, false: 0 };
    rows.forEach((item) => {
      if (String(item["EMSSTAT"]).toUpperCase() === "TRUE") counts.true += 1;
      else counts.false += 1;
    });
    return counts;
  }

  function redrawCharts(rows, compare) {
    const cmp = compare && compare.on;
    let dayOfWeekData;
    let dayTraces;
    if (cmp) {
      const a = aggregateData(compare.A, "Day of the Week");
      const b = aggregateData(compare.B, "Day of the Week");
      const ea = ensureAllDays(a);
      const eb = ensureAllDays(b);
      dayTraces = [
        { x: daysOfWeekLabels, y: ea.map((i) => i.count), name: "Period A", type: "bar" },
        { x: daysOfWeekLabels, y: eb.map((i) => i.count), name: "Period B", type: "bar" },
      ];
    } else {
      dayOfWeekData = ensureAllDays(aggregateData(rows, "Day of the Week"));
      dayTraces = [{ x: daysOfWeekLabels, y: dayOfWeekData.map((i) => i.count), type: "bar", name: "Incidents" }];
    }
    Plotly.newPlot(
      "day-of-week-plot",
      dayTraces,
      { title: "Incidents by Day of the Week", barmode: cmp ? "group" : "relative", xaxis: { title: "Day" } },
      { responsive: true }
    );

    let timeTraces;
    if (cmp) {
      const ta = aggregateData(compare.A, "Time of Day").sort((x, y) => Number(x.key) - Number(y.key));
      const tb = aggregateData(compare.B, "Time of Day").sort((x, y) => Number(x.key) - Number(y.key));
      timeTraces = [
        { x: ta.map((i) => i.key), y: ta.map((i) => i.count), name: "Period A", mode: "lines+markers", type: "scatter" },
        { x: tb.map((i) => i.key), y: tb.map((i) => i.count), name: "Period B", mode: "lines+markers", type: "scatter" },
      ];
    } else {
      const timeOfDayData = aggregateData(rows, "Time of Day").sort((a, b) => Number(a.key) - Number(b.key));
      timeTraces = [
        {
          x: timeOfDayData.map((i) => i.key),
          y: timeOfDayData.map((i) => i.count),
          type: "scatter",
          mode: "lines+markers",
        },
      ];
    }
    Plotly.newPlot(
      "time-of-day-plot",
      timeTraces,
      {
        title: "Incidents by Time of Day",
        xaxis: { title: "Hour", dtick: 1 },
        yaxis: { title: "Count" },
      },
      { responsive: true }
    );

    fetch("https://gist.githubusercontent.com/stellasphere/9490c195ed2b53c707087c8c2db4ec0c/raw/76b0cb0ef0bfd8a2ec988aa54e30ecd1b483495d/descriptions.json")
      .then((r) => r.json())
      .then((weatherIcons) => {
        let weatherData = aggregateData(rows, "Weather").filter((item) => item.key !== "Unknown");
        const weatherPlotData = [{ x: weatherData.map((i) => i.key), y: weatherData.map((i) => i.count), type: "bar" }];
        Plotly.newPlot(
          "weather-plot",
          weatherPlotData,
          { title: "Incidents by Weather", xaxis: { title: "WMO code", type: "category" }, yaxis: { title: "Count" } },
          { responsive: true }
        );
        const weatherIconsContainer = document.getElementById("weather-icons");
        if (!weatherIconsContainer) return;
        weatherIconsContainer.innerHTML = "";
        weatherData.forEach((item) => {
          const code = item.key;
          const dayIcon = weatherIcons[code]?.day?.image || "";
          const nightIcon = weatherIcons[code]?.night?.image || "";
          const dayDescription = weatherIcons[code]?.day?.description || "";
          const nightDescription = weatherIcons[code]?.night?.description || "";
          const description = dayDescription === nightDescription ? dayDescription : `${dayDescription} / ${nightDescription}`;
          const iconItem = document.createElement("div");
          iconItem.className = "weather-icon-item";
          iconItem.innerHTML = `<div class="code-cont"><strong>${code}</strong></div><div class="vertical"></div>
            ${dayIcon ? `<div class="icondesc"><img src="${dayIcon}" height="40">` : ""}
            ${nightIcon && dayIcon !== nightIcon ? ` <span class="separator">|</span> <img src="${nightIcon}" height="40">` : ""}
            <br>${description}</div>`;
          weatherIconsContainer.appendChild(iconItem);
        });
      })
      .catch(() => {});

    const topN = parseInt(document.getElementById("numIncidents").value, 10) || 20;
    const topNatureData = aggregateAndSortDataByKey(rows, "Nature", topN);
    const plotHeight = topN * 40;
    Plotly.newPlot(
      "incident-rank-plot",
      [
        {
          x: topNatureData.map((i) => i.count),
          y: topNatureData.map((i) => i.key),
          type: "bar",
          orientation: "h",
          text: topNatureData.map((i) => i.key),
          textposition: "inside",
          insidetextanchor: "middle",
          hoverinfo: "x+text",
        },
      ],
      {
        title: "Top " + topN + " Incident Types",
        xaxis: { title: "Count" },
        yaxis: { title: "Type", showticklabels: false, autorange: "reversed" },
        height: plotHeight,
        bargap: 0.1,
      },
      { responsive: true }
    );

    const emsstatData = aggregateEMSSTAT(rows);
    Plotly.newPlot(
      "emsstat-plot",
      [{ values: [emsstatData.true, emsstatData.false], labels: ["True", "False"], type: "pie" }],
      { title: "EMSSTAT" },
      { responsive: true }
    );

    const sideOfTownData = aggregateData(rows, "Side of Town");
    const sideOfTownOrder = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
    sideOfTownData.sort((a, b) => sideOfTownOrder.indexOf(a.key) - sideOfTownOrder.indexOf(b.key));
    const hi = sideOfTownData.map((i) => i.count).indexOf(Math.max(...sideOfTownData.map((i) => i.count)));
    Plotly.newPlot(
      "side-of-town-plot",
      [
        {
          values: sideOfTownData.map((i) => i.count),
          labels: sideOfTownData.map((i) => i.key),
          type: "pie",
          textinfo: "label+percent",
          insidetextorientation: "radial",
          pull: sideOfTownData.map((_, i) => (i === hi ? 0.1 : 0)),
        },
      ],
      { title: "Side of Town" },
      { responsive: true }
    );
  }

  window.updateIncidentChart = function () {
    const filtered = getActiveRows();
    redrawCharts(filtered, getComparePayload(filtered));
  };

  function getActiveRows() {
    const start = document.getElementById("filter-start").value;
    const end = document.getElementById("filter-end").value;
    return filterByRange(fullData, start, end);
  }

  function getComparePayload(rows) {
    const on = document.getElementById("compare-toggle").checked;
    if (!on) return null;
    const a0 = document.getElementById("cmp-a-start").value;
    const a1 = document.getElementById("cmp-a-end").value;
    const b0 = document.getElementById("cmp-b-start").value;
    const b1 = document.getElementById("cmp-b-end").value;
    if (!a0 || !a1 || !b0 || !b1) return null;
    return { on: true, ...splitCompare(rows, a0, a1, b0, b1) };
  }

  function getMapPoints(rows) {
    const pts = [];
    rows.forEach((r) => {
      const lat = parseFloat(r.Latitude);
      const lng = parseFloat(r.Longitude);
      if (!isNaN(lat) && !isNaN(lng)) pts.push({ lat, lng });
    });
    if (pts.length) return pts;
    locationsFallback.forEach((loc) => {
      const lat = parseFloat(loc.latitude);
      const lng = parseFloat(loc.longitude);
      if (!isNaN(lat) && !isNaN(lng)) {
        for (let i = 0; i < (loc.count || 1); i++) pts.push({ lat, lng });
      }
    });
    return pts;
  }

  let map;
  let markerLayer;
  let heatLayer;
  let clusterGroup;

  function buildMap(rows) {
    const el = document.getElementById("map");
    if (!el || typeof L === "undefined") return;
    if (map) {
      map.remove();
      map = null;
    }
    map = L.map("map").setView([35.2226, -97.4395], 12);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 16,
      attribution: "© OpenStreetMap",
    }).addTo(map);

    const pts = getMapPoints(rows);
    const heatData = pts.map((p) => [p.lat, p.lng, 0.4]);

    function getColors(count, maxC) {
      const intensity = maxC ? count / maxC : 0;
      const hue = (1 - intensity) * 120;
      return { fillColor: `hsl(${hue}, 100%, 50%)`, strokeColor: `hsl(${hue}, 100%, 30%)` };
    }

    const counts = {};
    pts.forEach((p) => {
      const k = `${p.lat.toFixed(5)},${p.lng.toFixed(5)}`;
      counts[k] = (counts[k] || 0) + 1;
    });
    const maxC = Math.max(1, ...Object.values(counts));

    const circles = [];
    pts.forEach((p) => {
      const k = `${p.lat.toFixed(5)},${p.lng.toFixed(5)}`;
      const c = counts[k] || 1;
      const col = getColors(c, maxC);
      const r = parseFloat(document.getElementById("map-radius").value) || 12;
      const mk = L.circleMarker([p.lat, p.lng], {
        color: col.strokeColor,
        fillColor: col.fillColor,
        fillOpacity: 0.9,
        radius: r + Math.sqrt(c),
      });
      mk.bindPopup("Incidents at/near this point: " + c);
      circles.push(mk);
    });

    if (document.getElementById("map-cluster").checked && typeof L.markerClusterGroup === "function") {
      clusterGroup = L.markerClusterGroup({ maxClusterRadius: 50 });
      circles.forEach((c) => clusterGroup.addLayer(c));
      map.addLayer(clusterGroup);
    } else {
      markerLayer = L.featureGroup(circles);
      map.addLayer(markerLayer);
    }
    if (typeof L.heatLayer === "function" && heatData.length) {
      heatLayer = L.heatLayer(heatData, { radius: 28, blur: 18, maxZoom: 14 });
    }
    if (document.getElementById("map-heat").checked && heatLayer) map.addLayer(heatLayer);
  }

  function refreshMap() {
    const rows = getActiveRows();
    buildMap(rows);
  }

  document.getElementById("apply-filters").addEventListener("click", () => {
    const filtered = getActiveRows();
    redrawCharts(filtered, getComparePayload(filtered));
    refreshMap();
  });

  document.getElementById("compare-toggle").addEventListener("change", () => {
    document.getElementById("compare-fields").style.display = document.getElementById("compare-toggle").checked ? "grid" : "none";
  });

  ["map-cluster", "map-heat", "map-radius"].forEach((id) => {
    const n = document.getElementById(id);
    if (n)
      n.addEventListener("change", () => {
        refreshMap();
      });
  });

  const filteredInit = getActiveRows();
  redrawCharts(filteredInit, getComparePayload(filteredInit));
  refreshMap();
})();
