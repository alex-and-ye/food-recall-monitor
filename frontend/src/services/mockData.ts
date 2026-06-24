import type { FoodRecallAlert } from "@/types/alert";

export const SIMULATE_EMPTY_DATABASE = false;

const MOCK_ALERTS: FoodRecallAlert[] = [
  {
    alert_id: "alert-001",
    product_name: "Organic Baby Spinach",
    product_category: "Produce",
    risk_level: "High",
    recall_reason: "Potential Listeria monocytogenes contamination",
    hazard_type: "Biological",
    summary:
      "Routine sampling detected Listeria in packaged organic baby spinach distributed to major grocery chains across the Midwest.",
    consumer_action:
      "Discard immediately and contact the retailer for a full refund. Do not consume even if washed.",
    affected_regions: ["Illinois", "Indiana", "Michigan", "Ohio", "Wisconsin"],
    recall_date: "2026-06-22",
    source_url: "https://www.fda.gov/food/recalls-outbreaks-emergencies",
  },
  {
    alert_id: "alert-002",
    product_name: "Valley Fresh Whole Milk (1 Gallon)",
    product_category: "Dairy",
    risk_level: "Medium",
    recall_reason: "Undeclared pasteurization equipment residue",
    hazard_type: "Chemical",
    summary:
      "A cleaning agent trace was found in a limited production batch of whole milk bottled at a regional dairy facility.",
    consumer_action:
      "Return unopened or partially used containers to the place of purchase for a refund.",
    affected_regions: ["California", "Nevada", "Arizona"],
    recall_date: "2026-06-22",
    source_url: "https://www.fda.gov/food/recalls-outbreaks-emergencies",
  },
  {
    alert_id: "alert-003",
    product_name: "Premium Ground Beef (80/20)",
    product_category: "Meat",
    risk_level: "High",
    recall_reason: "E. coli O157:H7 detected in production lot",
    hazard_type: "Biological",
    summary:
      "USDA-FSIS testing confirmed E. coli in ground beef produced on June 18. Products were shipped to retail and foodservice locations.",
    consumer_action:
      "Do not eat. Return to store or destroy. Cook all ground beef to 160°F if from an uncertain source.",
    affected_regions: ["Texas", "Oklahoma", "Louisiana", "Arkansas"],
    recall_date: "2026-06-21",
    source_url: "https://www.fsis.usda.gov/recalls",
  },
  {
    alert_id: "alert-004",
    product_name: "Sunrise Trail Mix (12 oz)",
    product_category: "Packaged Goods",
    risk_level: "Low",
    recall_reason: "Undeclared tree nuts (cashews)",
    hazard_type: "Allergen",
    summary:
      "Packaging error led to cashew inclusion in a nut-free labeled trail mix variant sold in club stores.",
    consumer_action:
      "Consumers with cashew allergies should not consume this product. Return for a full refund.",
    affected_regions: ["National"],
    recall_date: "2026-06-21",
    source_url: "https://www.fda.gov/food/recalls-outbreaks-emergencies",
  },
  {
    alert_id: "alert-005",
    product_name: "Romaine Hearts (3-Pack)",
    product_category: "Produce",
    risk_level: "High",
    recall_reason: "Salmonella contamination linked to irrigation water",
    hazard_type: "Biological",
    summary:
      "An outbreak investigation traced Salmonella illnesses to romaine hearts harvested from a single grower in Yuma County.",
    consumer_action:
      "Throw away all affected packages. Sanitize refrigerator drawers that held the product.",
    affected_regions: ["Arizona", "California", "Colorado", "New Mexico"],
    recall_date: "2026-06-20",
    source_url: "https://www.cdc.gov/foodborne-outbreaks",
  },
  {
    alert_id: "alert-006",
    product_name: "Artisan Brie Cheese Wheel",
    product_category: "Dairy",
    risk_level: "High",
    recall_reason: "Listeria monocytogenes in soft-ripened cheese",
    hazard_type: "Biological",
    summary:
      "Environmental swabbing at the creamery identified Listeria in the aging room affecting brie wheels distributed to specialty retailers.",
    consumer_action:
      "High-risk individuals including pregnant women should discard immediately. Contact your healthcare provider if consumed.",
    affected_regions: ["New York", "New Jersey", "Connecticut", "Pennsylvania"],
    recall_date: "2026-06-20",
    source_url: "https://www.fda.gov/food/recalls-outbreaks-emergencies",
  },
  {
    alert_id: "alert-007",
    product_name: "Smoked Turkey Breast Slices",
    product_category: "Meat",
    risk_level: "Medium",
    recall_reason: "Foreign material (plastic fragment) in sliced product",
    hazard_type: "Physical",
    summary:
      "A deli slicer component failure introduced small plastic fragments into pre-sliced smoked turkey breast packages.",
    consumer_action:
      "Inspect packages and return any product with visible foreign material. Report injuries to the company hotline.",
    affected_regions: ["Florida", "Georgia", "South Carolina", "North Carolina"],
    recall_date: "2026-06-19",
    source_url: "https://www.fsis.usda.gov/recalls",
  },
  {
    alert_id: "alert-008",
    product_name: "Honey Nut Cereal (Family Size)",
    product_category: "Packaged Goods",
    risk_level: "Low",
    recall_reason: "Undeclared wheat in gluten-free labeled batch",
    hazard_type: "Allergen",
    summary:
      "A mislabeling incident at the co-packer resulted in standard formula cereal placed in gluten-free labeled boxes.",
    consumer_action:
      "Individuals with celiac disease or wheat allergy should not consume. Return to retailer for replacement.",
    affected_regions: ["National"],
    recall_date: "2026-06-19",
    source_url: "https://www.fda.gov/food/recalls-outbreaks-emergencies",
  },
  {
    alert_id: "alert-009",
    product_name: "Pre-Cut Cantaloupe Chunks",
    product_category: "Produce",
    risk_level: "High",
    recall_reason: "Salmonella outbreak associated with fresh-cut melon",
    hazard_type: "Biological",
    summary:
      "Multistate illnesses have been linked to pre-cut cantaloupe sold in clamshell containers at grocery delis.",
    consumer_action:
      "Discard all recalled melon products. Wash hands and surfaces that contacted the product.",
    affected_regions: ["Illinois", "Missouri", "Iowa", "Kansas", "Nebraska"],
    recall_date: "2026-06-18",
    source_url: "https://www.cdc.gov/foodborne-outbreaks",
  },
  {
    alert_id: "alert-010",
    product_name: "Greek Yogurt Vanilla (32 oz)",
    product_category: "Dairy",
    risk_level: "Low",
    recall_reason: "Yeast fermentation causing package swelling",
    hazard_type: "Biological",
    summary:
      "Post-pasteurization yeast contamination caused bloated containers in a single production run of vanilla Greek yogurt.",
    consumer_action:
      "Do not open swollen containers. Return to store for a refund even without a receipt.",
    affected_regions: ["Oregon", "Washington", "Idaho"],
    recall_date: "2026-06-18",
    source_url: "https://www.fda.gov/food/recalls-outbreaks-emergencies",
  },
  {
    alert_id: "alert-011",
    product_name: "Italian Pork Sausage Links",
    product_category: "Meat",
    risk_level: "Medium",
    recall_reason: "Misbranding — undeclared milk allergen",
    hazard_type: "Allergen",
    summary:
      "A spice blend substitution introduced milk powder into a sausage recipe not listed on the ingredient panel.",
    consumer_action:
      "Consumers with milk allergy should not eat this product. Return for a full refund.",
    affected_regions: ["Minnesota", "Wisconsin", "North Dakota", "South Dakota"],
    recall_date: "2026-06-17",
    source_url: "https://www.fsis.usda.gov/recalls",
  },
  {
    alert_id: "alert-012",
    product_name: "Canned Tomato Sauce (24 oz)",
    product_category: "Packaged Goods",
    risk_level: "Medium",
    recall_reason: "Can seam defect — potential botulism risk",
    hazard_type: "Biological",
    summary:
      "Quality control identified incomplete double-seams on tomato sauce cans from one canning line shift.",
    consumer_action:
      "Do not use cans with leaks, bulges, or spurting liquid. Return affected cans to the retailer.",
    affected_regions: ["National"],
    recall_date: "2026-06-17",
    source_url: "https://www.fda.gov/food/recalls-outbreaks-emergencies",
  },
  {
    alert_id: "alert-013",
    product_name: "Organic Strawberries (1 lb)",
    product_category: "Produce",
    risk_level: "Medium",
    recall_reason: "Cyclospora detected on imported berries",
    hazard_type: "Biological",
    summary:
      "FDA import screening found Cyclospora on organic strawberries sourced from a supplier in Baja California.",
    consumer_action:
      "Discard the product. Seek medical attention if you experience prolonged diarrhea after consumption.",
    affected_regions: ["California", "Texas", "Arizona", "New Mexico"],
    recall_date: "2026-06-16",
    source_url: "https://www.fda.gov/food/recalls-outbreaks-emergencies",
  },
  {
    alert_id: "alert-014",
    product_name: "Sharp Cheddar Cheese Block",
    product_category: "Dairy",
    risk_level: "Low",
    recall_reason: "Incorrect best-by date on packaging",
    hazard_type: "Labeling",
    summary:
      "A printer calibration error applied incorrect expiration dates to sharp cheddar blocks shipped to warehouse clubs.",
    consumer_action:
      "Product is safe if stored properly. Return for exchange if the date causes concern.",
    affected_regions: ["Colorado", "Utah", "Wyoming", "Montana"],
    recall_date: "2026-06-16",
    source_url: "https://www.fda.gov/food/recalls-outbreaks-emergencies",
  },
  {
    alert_id: "alert-015",
    product_name: "Chicken Nuggets (Frozen, 2 lb)",
    product_category: "Meat",
    risk_level: "High",
    recall_reason: "Metal fragments found in breading line",
    hazard_type: "Physical",
    summary:
      "A metal detector failure allowed small stainless steel fragments into frozen breaded chicken nugget packages.",
    consumer_action:
      "Do not consume. Return to place of purchase. Report any injury or illness to the manufacturer.",
    affected_regions: ["National"],
    recall_date: "2026-06-15",
    source_url: "https://www.fsis.usda.gov/recalls",
  },
  {
    alert_id: "alert-016",
    product_name: "Dark Chocolate Bar (85% Cacao)",
    product_category: "Packaged Goods",
    risk_level: "Low",
    recall_reason: "Undeclared soy lecithin",
    hazard_type: "Allergen",
    summary:
      "An emulsifier change was not reflected on updated packaging for a premium dark chocolate bar line.",
    consumer_action:
      "Those with soy allergy should avoid this product. Return unopened bars for a refund.",
    affected_regions: ["New England"],
    recall_date: "2026-06-15",
    source_url: "https://www.fda.gov/food/recalls-outbreaks-emergencies",
  },
  {
    alert_id: "alert-017",
    product_name: "Bagged Salad Spring Mix",
    product_category: "Produce",
    risk_level: "Medium",
    recall_reason: "Potential parasite contamination (Cyclospora)",
    hazard_type: "Biological",
    summary:
      "FDA traceback identified a common supplier for bagged spring mix implicated in a regional Cyclospora cluster.",
    consumer_action:
      "Discard recalled salad mixes. Wash reusable bags that held the product.",
    affected_regions: ["Mid-Atlantic"],
    recall_date: "2026-06-14",
    source_url: "https://www.fda.gov/food/recalls-outbreaks-emergencies",
  },
  {
    alert_id: "alert-018",
    product_name: "Unsalted Butter (4 Sticks)",
    product_category: "Dairy",
    risk_level: "Medium",
    recall_reason: "Elevated coliform bacteria in cream supply",
    hazard_type: "Biological",
    summary:
      "Supplier testing showed elevated coliform counts in cream used for a single day of butter production.",
    consumer_action:
      "Return affected packages to the retailer. Cooking may not eliminate all risks — discard is recommended.",
    affected_regions: ["Kentucky", "Tennessee", "Virginia", "West Virginia"],
    recall_date: "2026-06-14",
    source_url: "https://www.fda.gov/food/recalls-outbreaks-emergencies",
  },
  {
    alert_id: "alert-019",
    product_name: "Beef Frankfurters (8-Pack)",
    product_category: "Meat",
    risk_level: "High",
    recall_reason: "Listeria monocytogenes in ready-to-eat franks",
    hazard_type: "Biological",
    summary:
      "Environmental monitoring at the plant detected Listeria on a surface that contacts finished frankfurter products.",
    consumer_action:
      "Do not eat, even if reheated. Return to store or discard in a sealed bag.",
    affected_regions: ["Ohio", "Pennsylvania", "Michigan"],
    recall_date: "2026-06-13",
    source_url: "https://www.fsis.usda.gov/recalls",
  },
  {
    alert_id: "alert-020",
    product_name: "Instant Ramen Chicken Flavor",
    product_category: "Packaged Goods",
    risk_level: "Low",
    recall_reason: "Undeclared sesame in seasoning packet",
    hazard_type: "Allergen",
    summary:
      "A supplier reformulated the seasoning blend to include sesame oil without notifying the brand owner.",
    consumer_action:
      "Consumers with sesame allergy should not consume. Return for a full refund.",
    affected_regions: ["National"],
    recall_date: "2026-06-13",
    source_url: "https://www.fda.gov/food/recalls-outbreaks-emergencies",
  },
  {
    alert_id: "alert-021",
    product_name: "Fresh Basil (Potted, 4 oz)",
    product_category: "Produce",
    risk_level: "Low",
    recall_reason: "Pesticide residue above tolerance level",
    hazard_type: "Chemical",
    summary:
      "State agriculture testing found chlorpyrifos residues exceeding EPA tolerance on fresh basil from one greenhouse lot.",
    consumer_action:
      "Discard affected basil. Wash hands after handling. Potted plants should not be consumed.",
    affected_regions: ["Florida"],
    recall_date: "2026-06-12",
    source_url: "https://www.fda.gov/food/recalls-outbreaks-emergencies",
  },
  {
    alert_id: "alert-022",
    product_name: "Chocolate Milk (Half Gallon)",
    product_category: "Dairy",
    risk_level: "Medium",
    recall_reason: "Insufficient pasteurization time on one processing line",
    hazard_type: "Biological",
    summary:
      "A valve malfunction shortened hold time on a chocolate milk batch, potentially allowing pathogen survival.",
    consumer_action:
      "Do not drink affected cartons. Return to the retailer with the lot code visible.",
    affected_regions: ["Georgia", "Alabama", "Mississippi"],
    recall_date: "2026-06-12",
    source_url: "https://www.fda.gov/food/recalls-outbreaks-emergencies",
  },
  {
    alert_id: "alert-023",
    product_name: "Boneless Pork Loin Chops",
    product_category: "Meat",
    risk_level: "Medium",
    recall_reason: "Salmonella in raw pork products",
    hazard_type: "Biological",
    summary:
      "USDA sampling confirmed Salmonella in boneless pork loin chops from a facility with repeat non-compliance findings.",
    consumer_action:
      "Cook pork to an internal temperature of 145°F with a 3-minute rest, or return for refund if from recalled lot.",
    affected_regions: ["Iowa", "Illinois", "Missouri"],
    recall_date: "2026-06-11",
    source_url: "https://www.fsis.usda.gov/recalls",
  },
  {
    alert_id: "alert-024",
    product_name: "Gluten-Free Crackers (Box)",
    product_category: "Packaged Goods",
    risk_level: "High",
    recall_reason: "Undeclared gluten — wheat flour cross-contact",
    hazard_type: "Allergen",
    summary:
      "Shared equipment at the bakery caused wheat flour cross-contact in crackers labeled and certified gluten-free.",
    consumer_action:
      "Individuals with celiac disease or wheat allergy must not consume. Return for a full refund.",
    affected_regions: ["National"],
    recall_date: "2026-06-11",
    source_url: "https://www.fda.gov/food/recalls-outbreaks-emergencies",
  },
  {
    alert_id: "alert-025",
    product_name: "Sliced Mushrooms (8 oz)",
    product_category: "Produce",
    risk_level: "Low",
    recall_reason: "Potential glass fragments from packaging equipment",
    hazard_type: "Physical",
    summary:
      "A worn cutting blade on the packaging line may have introduced microscopic glass into sliced mushroom containers.",
    consumer_action:
      "Inspect contents before use. Return any package with visible glass or unusual texture.",
    affected_regions: ["Pacific Northwest"],
    recall_date: "2026-06-10",
    source_url: "https://www.fda.gov/food/recalls-outbreaks-emergencies",
  },
  {
    alert_id: "alert-026",
    product_name: "Cottage Cheese (16 oz)",
    product_category: "Dairy",
    risk_level: "High",
    recall_reason: "Listeria monocytogenes in curd processing area",
    hazard_type: "Biological",
    summary:
      "Whole-genome sequencing linked patient isolates to Listeria found in the cottage cheese production environment.",
    consumer_action:
      "Discard all recalled cottage cheese immediately. Clean refrigerator surfaces that contacted the product.",
    affected_regions: ["Michigan", "Indiana", "Ohio"],
    recall_date: "2026-06-10",
    source_url: "https://www.fda.gov/food/recalls-outbreaks-emergencies",
  },
  {
    alert_id: "alert-027",
    product_name: "Deli Ham Off-the-Bone",
    product_category: "Meat",
    risk_level: "Low",
    recall_reason: "Sodium content mislabeled on nutrition facts panel",
    hazard_type: "Labeling",
    summary:
      "Laboratory verification showed sodium levels 40% higher than printed on deli ham nutrition labels.",
    consumer_action:
      "Those on sodium-restricted diets should avoid this product. Return for exchange or refund.",
    affected_regions: ["Northeast"],
    recall_date: "2026-06-09",
    source_url: "https://www.fsis.usda.gov/recalls",
  },
];

const LATENCY_MS = 1200;

export function fetchMockAlerts(): Promise<FoodRecallAlert[]> {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve(SIMULATE_EMPTY_DATABASE ? [] : MOCK_ALERTS);
    }, LATENCY_MS);
  });
}
