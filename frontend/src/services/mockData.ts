// TODO: Remove this before final project delivery

import { filterAlerts, type AlertSearchPayload } from "@/lib/alertSearch";
import type { GetAlertsParams } from "@/services/api/client";
import { ApiError } from "@/services/api/errors";
import type { FoodRecallAlert, FoodRecallAlertStats, FoodRecallAlertsVersion } from "@/types/alert";

const MOCK_ALERTS: FoodRecallAlert[] = [
  {
    alert_id: "mock-alert-001",
    web_source: "uk",
    country_source: "UK",
    product_name: "Organic Baby Spinach",
    product_category: "Produce",
    risk_level: "High",
    recall_reason: "Potential Listeria monocytogenes contamination",
    hazard_type: "Biological",
    summary:
      "Routine sampling detected Listeria in packaged organic baby spinach distributed to major grocery chains.",
    consumer_action:
      "Discard immediately and contact the retailer for a full refund.",
    batch_id: "LOT-OBS-22618; Best before 2026-07-05",
    affected_regions: ["England", "Scotland", "Wales"],
    recall_date: "2026-06-22",
    source_url: "https://www.food.gov.uk/",
    latitude: 52.4862,
    longitude: -1.8904,
  },
  {
    alert_id: "mock-alert-002",
    web_source: "germany",
    country_source: "Germany",
    product_name: "Valley Fresh Whole Milk (1L)",
    product_category: "Dairy",
    risk_level: "Medium",
    recall_reason: "Undeclared pasteurization equipment residue",
    hazard_type: "Chemical",
    summary:
      "A cleaning agent trace was found in a limited production batch of whole milk bottled at a regional dairy facility.",
    consumer_action:
      "Return unopened or partially used containers to the place of purchase for a refund.",
    batch_id: "LPK1WA046; LPK1WA048; LPK1WA050",
    affected_regions: ["Bavaria", "Berlin", "Hamburg"],
    recall_date: "2026-06-21",
    source_url: "https://www.bvl.bund.de/",
    latitude: 48.7904,
    longitude: 11.4979,
  },
  {
    alert_id: "mock-alert-003",
    web_source: "france",
    country_source: "France",
    product_name: "Sunrise Trail Mix (340g)",
    product_category: "Packaged Goods",
    risk_level: "Low",
    recall_reason: "Undeclared tree nuts (cashews)",
    hazard_type: "Allergen",
    summary:
      "Packaging error led to cashew inclusion in a nut-free labeled trail mix variant sold in club stores.",
    consumer_action:
      "Consumers with cashew allergies should not consume this product. Return for a full refund.",
    batch_id: "STM-340-0612",
    affected_regions: ["Île-de-France", "Provence"],
    recall_date: "2026-06-20",
    source_url: "https://rappel.conso.gouv.fr/",
    latitude: 48.8566,
    longitude: 2.3522,
  },
  {
    alert_id: "mock-alert-004",
    web_source: "uk",
    country_source: "UK",
    product_name: "Premium Ground Beef (80/20)",
    product_category: "Meat",
    risk_level: "High",
    recall_reason: "E. coli O157:H7 detected in production lot",
    hazard_type: "Biological",
    summary:
      "Testing confirmed E. coli in ground beef produced on June 18. Products were shipped to retail locations.",
    consumer_action:
      "Do not eat. Return to store or destroy. Cook all ground beef to 160°F if from an uncertain source.",
    batch_id: "Est. 12345; Packed 2026-06-18",
    affected_regions: ["Northern Ireland", "England"],
    recall_date: "2026-06-19",
    source_url: "https://www.food.gov.uk/",
    latitude: 54.7877,
    longitude: -6.4923,
  },
  {
    alert_id: "mock-alert-005",
    web_source: "germany",
    country_source: "Germany",
    product_name: "Romaine Hearts (3-Pack)",
    product_category: "Produce",
    risk_level: "Medium",
    recall_reason: "Salmonella contamination linked to irrigation water",
    hazard_type: "Biological",
    summary:
      "An outbreak investigation traced Salmonella illnesses to romaine hearts harvested from a single grower.",
    consumer_action:
      "Throw away all affected packages. Sanitize refrigerator drawers that held the product.",
    batch_id: "",
    affected_regions: ["North Rhine-Westphalia", "Lower Saxony"],
    recall_date: "2026-06-18",
    source_url: "https://www.bvl.bund.de/",
    latitude: 51.4332,
    longitude: 7.6616,
  },
];

function toSearchPayload(params: GetAlertsParams): AlertSearchPayload {
  return {
    search: params.search ?? "",
    risk_level:
      params.risk_level === "High" ||
      params.risk_level === "Medium" ||
      params.risk_level === "Low"
        ? params.risk_level
        : null,
    country_source:
      params.country_source === "UK" ||
      params.country_source === "Germany" ||
      params.country_source === "France"
        ? params.country_source
        : null,
    recall_date: params.recall_date?.trim() || null,
    sort_by:
      params.sort_by === "latest" || params.sort_by === "oldest"
        ? params.sort_by
        : null,
  };
}

function buildMockStats(alerts: FoodRecallAlert[]): FoodRecallAlertStats {
  if (alerts.length === 0) {
    return {
      total_alerts: 0,
      top_5_hazard_types: [],
      top_5_product_categories: [],
      top_5_affected_regions: [],
      alerts_last_7_days: 0,
      alerts_last_30_days: 0,
    };
  }

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const sevenDaysAgo = new Date(today);
  sevenDaysAgo.setDate(today.getDate() - 7);
  const thirtyDaysAgo = new Date(today);
  thirtyDaysAgo.setDate(today.getDate() - 30);

  const hazardTypes = new Map<string, number>();
  const productCategories = new Map<string, number>();
  const affectedRegions = new Map<string, number>();
  let alertsLast7Days = 0;
  let alertsLast30Days = 0;

  for (const alert of alerts) {
    hazardTypes.set(alert.hazard_type, (hazardTypes.get(alert.hazard_type) ?? 0) + 1);
    productCategories.set(
      alert.product_category,
      (productCategories.get(alert.product_category) ?? 0) + 1,
    );
    for (const region of alert.affected_regions) {
      affectedRegions.set(region, (affectedRegions.get(region) ?? 0) + 1);
    }

    const recallDate = new Date(`${alert.recall_date}T00:00:00`);
    if (recallDate >= sevenDaysAgo) {
      alertsLast7Days += 1;
    }
    if (recallDate >= thirtyDaysAgo) {
      alertsLast30Days += 1;
    }
  }

  const toTopFive = (counts: Map<string, number>): [string, number][] =>
    [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);

  return {
    total_alerts: alerts.length,
    top_5_hazard_types: toTopFive(hazardTypes),
    top_5_product_categories: toTopFive(productCategories),
    top_5_affected_regions: toTopFive(affectedRegions),
    alerts_last_7_days: alertsLast7Days,
    alerts_last_30_days: alertsLast30Days,
  };
}

export async function fetchMockAlerts(
  params: GetAlertsParams = {},
): Promise<FoodRecallAlert[]> {
  return filterAlerts(MOCK_ALERTS, toSearchPayload(params));
}

export async function fetchMockAlertById(id: string): Promise<FoodRecallAlert> {
  const alert = MOCK_ALERTS.find((item) => item.alert_id === id);
  if (!alert) {
    throw new ApiError("Alert not found", 404);
  }
  return alert;
}

export async function fetchMockStats(): Promise<FoodRecallAlertStats> {
  return buildMockStats(MOCK_ALERTS);
}

export async function fetchMockAlertsVersion(): Promise<FoodRecallAlertsVersion> {
  const sortedIds = MOCK_ALERTS.map((alert) => alert.alert_id).sort();
  return {
    count: sortedIds.length,
    fingerprint: sortedIds.join(","),
  };
}
