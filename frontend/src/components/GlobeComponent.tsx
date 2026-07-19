"use client";

import { useEffect, useRef, useState } from "react";
import Globe, { type GlobeMethods } from "react-globe.gl";
import type { FoodRecallAlert, RiskLevel } from "@/types/alert";

const COUNTRIES_GEOJSON_URL =
  "https://cdn.jsdelivr.net/gh/vasturiano/react-globe.gl@master/example/datasets/ne_110m_admin_0_countries.geojson";

interface GeoJsonGeometry {
  type: string;
  coordinates: number[] | number[][] | number[][][] | number[][][][];
}

interface CountryFeature {
  type: string;
  properties: Record<string, unknown>;
  geometry: GeoJsonGeometry;
}

interface CountriesGeoJson {
  type: string;
  features: CountryFeature[];
}

interface GlobePoint extends FoodRecallAlert {
  lat: number;
  lng: number;
  selected: boolean;
}

interface GlobeComponentProps {
  alerts: FoodRecallAlert[];
  selectedAlertId: string | null;
  onPointClick: (alert: FoodRecallAlert) => void;
}

const RISK_PIN_COLORS: Record<RiskLevel, string> = {
  High: "#b91c1c",
  Medium: "#f59e0b",
  Low: "#047857",
  Unknown: "#475569",
};

function toGlobePoints(
  alerts: FoodRecallAlert[],
  selectedAlertId: string | null,
): GlobePoint[] {
  return alerts.map((alert) => ({
    ...alert,
    lat: alert.latitude,
    lng: alert.longitude,
    selected: alert.alert_id === selectedAlertId,
  }));
}

function riskColor(riskLevel: RiskLevel): string {
  return RISK_PIN_COLORS[riskLevel] ?? "#475569";
}

function createPinElement(
  alert: GlobePoint,
  onPointClick: (alert: FoodRecallAlert) => void,
): HTMLElement {
  const color = riskColor(alert.risk_level);
  const isSelected = alert.selected;
  const size = isSelected ? 40 : 28;
  const height = isSelected ? 52 : 36;

  const wrapper = document.createElement("button");
  wrapper.type = "button";
  wrapper.setAttribute(
    "aria-label",
    isSelected
      ? `Selected alert: ${alert.product_name}`
      : `Open alert for ${alert.product_name}`,
  );
  wrapper.setAttribute("aria-pressed", isSelected ? "true" : "false");
  wrapper.dataset.selected = isSelected ? "true" : "false";
  wrapper.style.cssText = [
    "background: transparent",
    "border: 0",
    "padding: 0",
    "cursor: pointer",
    "transform: translate(-50%, -100%)",
    "pointer-events: auto",
    "transition: opacity 150ms ease, filter 150ms ease",
    isSelected
      ? "opacity: 1; filter: drop-shadow(0 0 10px rgba(52, 211, 153, 0.95)) drop-shadow(0 0 4px rgba(255, 255, 255, 0.9)); z-index: 2;"
      : "opacity: 0.85; filter: none; z-index: 1;",
  ].join(";");

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", String(size));
  svg.setAttribute("height", String(height));
  svg.setAttribute("viewBox", "0 0 28 36");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = isSelected
    ? `
    <path
      d="M14 0C6.268 0 0 6.268 0 14c0 9.75 14 22 14 22s14-12.25 14-22C28 6.268 21.732 0 14 0z"
      fill="${color}"
      stroke="#ecfdf5"
      stroke-width="2.5"
    />
    <circle cx="14" cy="14" r="6.2" fill="#ecfdf5" />
    <circle cx="14" cy="14" r="3.2" fill="${color}" />
  `
    : `
    <path
      d="M14 0C6.268 0 0 6.268 0 14c0 9.75 14 22 14 22s14-12.25 14-22C28 6.268 21.732 0 14 0z"
      fill="${color}"
      stroke="#0f172a"
      stroke-width="1.5"
    />
    <circle cx="14" cy="14" r="5.5" fill="#f8fafc" />
  `;

  wrapper.appendChild(svg);
  wrapper.addEventListener("click", (event) => {
    event.stopPropagation();
    onPointClick(alert);
  });
  return wrapper;
}

export default function GlobeComponent({
  alerts,
  selectedAlertId,
  onPointClick,
}: GlobeComponentProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const globeRef = useRef<GlobeMethods | undefined>(undefined);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [countries, setCountries] = useState<CountryFeature[]>([]);

  const pointsData = toGlobePoints(alerts, selectedAlertId);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    const updateSize = () => {
      setDimensions({
        width: container.clientWidth,
        height: container.clientHeight,
      });
    };

    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let cancelled = false;

    fetch(COUNTRIES_GEOJSON_URL)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Failed to load countries GeoJSON (${response.status})`);
        }
        return response.json() as Promise<CountriesGeoJson>;
      })
      .then((data) => {
        if (!cancelled) {
          setCountries(data.features);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCountries([]);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const globe = globeRef.current;
    if (!globe) {
      return;
    }

    const controls = globe.controls();
    controls.autoRotate = false;
    controls.enableZoom = true;
    controls.enablePan = false;
  }, [dimensions.width, dimensions.height]);

  return (
    <div ref={containerRef} className="h-full w-full bg-slate-950">
      {dimensions.width > 0 && dimensions.height > 0 ? (
        <Globe
          ref={globeRef}
          width={dimensions.width}
          height={dimensions.height}
          backgroundColor="#020617"
          showAtmosphere
          atmosphereColor="#34d399"
          atmosphereAltitude={0.18}
          globeImageUrl="//cdn.jsdelivr.net/npm/three-globe/example/img/earth-dark.jpg"
          hexPolygonsData={countries}
          hexPolygonGeoJsonGeometry="geometry"
          hexPolygonColor={() => "#64748b"}
          hexPolygonAltitude={0.005}
          hexPolygonResolution={3}
          hexPolygonMargin={0.35}
          hexPolygonUseDots
          hexPolygonDotResolution={4}
          htmlElementsData={pointsData}
          htmlLat="lat"
          htmlLng="lng"
          htmlAltitude={0.02}
          htmlElement={(point: object) =>
            createPinElement(point as GlobePoint, onPointClick)
          }
          htmlElementVisibilityModifier={(element: HTMLElement, isVisible: boolean) => {
            if (!isVisible) {
              element.style.opacity = "0";
              return;
            }
            element.style.opacity =
              element.dataset.selected === "true" ? "1" : "0.85";
          }}
        />
      ) : null}
    </div>
  );
}
