export type NodeCategory = "Trigger" | "AI" | "Logic" | "Action";

export type CatalogItem = {
  type: string;
  label: string;
  category: NodeCategory;
  description: string;
  logic?: boolean;
};

export const CATALOG: CatalogItem[] = [
  { type: "manual_trigger", label: "Manual trigger", category: "Trigger", description: "Starts when you press Run and passes the text you enter." },
  { type: "document_uploaded", label: "Document uploaded", category: "Trigger", description: "Reads a document you choose when you press Run." },
  { type: "dataset_uploaded", label: "Dataset uploaded", category: "Trigger", description: "Reads the saved profile of a dataset you choose when you press Run." },
  { type: "summarise_text", label: "Summarise text", category: "AI", description: "Asks the model for a short summary of the previous text." },
  { type: "extract_information", label: "Extract information", category: "AI", description: "Asks the model for the fields you list, then checks that each one came back." },
  { type: "classify_content", label: "Classify content", category: "AI", description: "Asks the model to choose one of the labels you list." },
  { type: "generate_response", label: "Generate response", category: "AI", description: "Asks the model to write a response from the previous text." },
  { type: "analyse_document", label: "Analyse document", category: "AI", description: "Asks the model one question about the previous text." },
  { type: "condition", label: "If / else", category: "Logic", description: "Compares one field with a value and follows Yes or No.", logic: true },
  { type: "compare_values", label: "Compare values", category: "Logic", description: "Compares two fields, or a field and a value.", logic: true },
  { type: "field_exists", label: "Field exists", category: "Logic", description: "Follows Yes when the field has a value.", logic: true },
  { type: "save_result", label: "Save result", category: "Action", description: "Stores the current text on this run." },
  { type: "update_status", label: "Update status", category: "Action", description: "Sets this workflow to draft, active, or paused after the step succeeds." },
  { type: "create_notification", label: "Create notification", category: "Action", description: "Leaves a notification on this run. It is not emailed." },
  { type: "generate_report", label: "Generate report", category: "Action", description: "Assembles the current text into a report stored on this run." },
];

export const catalogByType = Object.fromEntries(CATALOG.map((item) => [item.type, item]));

export const OPERATORS = [
  ["eq", "is"],
  ["ne", "is not"],
  ["contains", "contains"],
  ["gt", "is greater than"],
  ["lt", "is less than"],
  ["gte", "is at least"],
  ["lte", "is at most"],
] as const;

export function defaultConfig(type: string): Record<string, string | string[]> {
  switch (type) {
    case "summarise_text":
      return { instruction: "Summarise the text in one short paragraph." };
    case "extract_information":
      return { fields: ["name", "date"] };
    case "classify_content":
      return { labels: ["Approve", "Review", "Reject"] };
    case "generate_response":
      return { instruction: "Write a short response." };
    case "analyse_document":
      return { question: "What are the main points?" };
    case "condition":
      return { field: "label", operator: "eq", value: "" };
    case "compare_values":
      return { left_field: "text", operator: "eq", right_value: "" };
    case "field_exists":
      return { field: "text" };
    case "save_result":
      return { name: "Result" };
    case "update_status":
      return { status: "active" };
    case "create_notification":
      return { title: "Workflow update" };
    case "generate_report":
      return { title: "Report" };
    default:
      return {};
  }
}

export function configForSave(type: string, config: Record<string, string | string[]>) {
  const next: Record<string, string | string[]> = { ...config };
  if (type === "compare_values") {
    if (textValue(next.right_field)) delete next.right_value;
    else delete next.right_field;
  }
  return next;
}

export function textValue(value: string | string[] | undefined) {
  return typeof value === "string" ? value : "";
}

export function listValue(value: string | string[] | undefined) {
  return Array.isArray(value) ? value : [];
}

export function durationLabel(ms: number | null) {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export function stepLabel(status: string, output: Record<string, unknown> | null) {
  if (status === "cancelled" && output?.skipped === true) {
    const reason = typeof output.reason === "string" ? output.reason : "";
    return reason.startsWith("Stopped") ? "Stopped" : "Skipped";
  }
  if (status === "succeeded") return "Succeeded";
  if (status === "failed") return "Failed";
  return status;
}