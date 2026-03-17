import { App } from "@modelcontextprotocol/ext-apps";
import Map from "ol/Map";
import View from "ol/View";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import VectorSource from "ol/source/Vector";
import XYZ from "ol/source/XYZ";
import GeoJSON from "ol/format/GeoJSON";
import { fromLonLat } from "ol/proj";
import "ol/ol.css";

// --- Map setup ---

const vectorSource = new VectorSource();

const map = new Map({
  target: "map",
  layers: [
    new TileLayer({
      className: "osm-layer",
      source: new XYZ({
        url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        minZoom: 0,
        maxZoom: 19,
        attributions: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      }),
    }),
    new VectorLayer({
      source: vectorSource,
      style: [
        {
          filter: ["==", ["get", "role"], "search_area"],
          style: {
            "stroke-color": "#03B000",
            "stroke-width": 3,
            "fill-color": "rgba(3, 176, 0, 0.15)",
            "circle-radius": 7,
            "circle-fill-color": "#03B000",
            "circle-stroke-color": "#029000",
            "circle-stroke-width": 2,
          },
        },
        {
          filter: ["!=", ["get", "role"], "search_area"],
          style: {
            "stroke-color": "#8E8B8B",
            "stroke-width": 2,
            "fill-color": "rgba(3, 0, 176, 0.1)",
            "circle-radius": 5,
            "circle-fill-color": "#CFCECD",
            "circle-stroke-color": "#8E8B8B",
            "circle-stroke-width": 1,
          },
        },
      ],
    }),
  ],
  view: new View({
    center: fromLonLat([8.2275, 46.8182]), // Switzerland
    zoom: 8,
  }),
});

// --- UI elements ---

const statusEl = document.getElementById("status")!;
const queryInput = document.getElementById("query-input") as HTMLInputElement;
const searchBtn = document.getElementById("search-btn") as HTMLButtonElement;

// --- MCP App ---

const app = new App({ name: "etter", version: "1.0.0" });
app.connect();

interface GeoQueryResult {
  query: string;
  geo_query: {
    reference_location: { name: string };
    spatial_relation: { relation: string };
  };
  result: object;
}

function displayResult(raw: string): void {
  const data = JSON.parse(raw) as GeoQueryResult;

  vectorSource.clear();
  const features = new GeoJSON({
    dataProjection: "EPSG:4326",
    featureProjection: "EPSG:3857",
  }).readFeatures(data.result);
  vectorSource.addFeatures(features);

  // Keep the search bar in sync with the query that produced this result
  if (data.query) {
    queryInput.value = data.query;
  }

  const extent = vectorSource.getExtent();
  if (features.length > 0 && extent) {
    map.getView().fit(extent, { padding: [60, 60, 60, 60], duration: 800, maxZoom: 14 });
    const { name } = data.geo_query.reference_location;
    const { relation } = data.geo_query.spatial_relation;
    statusEl.innerHTML = `<strong>${name}</strong> — ${relation}`;
  } else {
    statusEl.textContent = "No results found.";
  }
}

function showResult(result: { content?: Array<{ type: string; text?: string }> }): void {
  const text = result.content?.find((c) => c.type === "text")?.text;
  if (!text) {
    statusEl.textContent = "No result.";
    return;
  }
  try {
    displayResult(text);
  } catch (err) {
    statusEl.textContent = `Parse error: ${err}`;
  }
}

// When the host invokes the tool, pre-populate the search bar and show a loading state
app.ontoolinput = (params: { arguments?: Record<string, unknown> }) => {
  const query = params.arguments?.user_query;
  if (typeof query === "string") {
    queryInput.value = query;
  }
  statusEl.textContent = "Processing…";
};

// Receive result pushed by the host when tool is called from Copilot Chat
app.ontoolresult = showResult;

searchBtn.addEventListener("click", async () => {
  const query = queryInput.value.trim();
  if (!query) return;
  statusEl.textContent = "Searching…";
  searchBtn.disabled = true;
  try {
    const result = await app.callServerTool({ name: "parse_geo_query", arguments: { user_query: query } });
    showResult(result);
  } catch (err) {
    statusEl.textContent = `Error: ${err}`;
  } finally {
    searchBtn.disabled = false;
  }
});
