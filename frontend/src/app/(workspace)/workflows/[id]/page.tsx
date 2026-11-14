"use client";

import { useParams } from "next/navigation";
import { WorkflowBuilder } from "@/components/workflow-builder";

export default function WorkflowEditorPage() {
  const params = useParams<{ id: string }>();
  const id = Array.isArray(params.id) ? params.id[0] : params.id;
  if (!id) return null;
  return <WorkflowBuilder workflowId={id} />;
}
