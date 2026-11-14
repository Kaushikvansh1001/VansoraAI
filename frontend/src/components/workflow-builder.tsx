"use client";

import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, memo, useCallback, useEffect, useMemo, useState } from "react";
import { buttonClass, fieldClass } from "@/components/auth-card";
import { ApiError, api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { AnalystDataset, KnowledgeDocument, WorkflowDetail, WorkflowExecution } from "@/lib/types";
import {
  CATALOG,
  OPERATORS,
  catalogByType,
  configForSave,
  defaultConfig,
  durationLabel,
  listValue,
  stepLabel,
  textValue,
} from "@/lib/workflow-catalog";

type WorkflowNodeData = {
  nodeType: string;
  label: string;
  config: Record<string, string | string[]>;
};

type FlowNode = Node<WorkflowNodeData, "workflow">;

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function WorkflowBuilder({ workflowId }: { workflowId: string }) {
  return (
    <ReactFlowProvider>
      <Builder workflowId={workflowId} />
    </ReactFlowProvider>
  );
}

function Builder({ workflowId }: { workflowId: string }) {
  const router = useRouter();
  const { organization, organizationId } = useSession();
  const { screenToFlowPosition } = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [currentId, setCurrentId] = useState<string | null>(workflowId === "new" ? null : workflowId);
  const [name, setName] = useState("Untitled workflow");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState<"draft" | "active" | "paused">("draft");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [datasets, setDatasets] = useState<AnalystDataset[]>([]);
  const [runs, setRuns] = useState<WorkflowExecution[]>([]);
  const [runText, setRunText] = useState("");
  const [documentId, setDocumentId] = useState("");
  const [datasetId, setDatasetId] = useState("");
  const [latest, setLatest] = useState<WorkflowExecution | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(workflowId !== "new");
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);

  const selected = nodes.find((node) => node.id === selectedId) ?? null;
  const trigger = nodes.find((node) => catalogByType[node.data.nodeType]?.category === "Trigger");

  useEffect(() => {
    if (workflowId !== "new") return;
    setNodes((current) => (current.length > 0 ? current : [blankNode()]));
  }, [setNodes, workflowId]);

  useEffect(() => {
    if (!organizationId || workflowId === "new") return;
    let active = true;
    api<WorkflowDetail>(`/workflows/${workflowId}`, { orgId: organizationId })
      .then((workflow) => {
        if (!active) return;
        setCurrentId(workflow.id);
        setName(workflow.name);
        setDescription(workflow.description ?? "");
        setStatus(workflow.status);
        setNodes(workflow.nodes.map(toNode));
        setEdges(workflow.edges.map(toEdge));
        setLoading(false);
      })
      .catch((caught) => {
        if (!active) return;
        setError(caught instanceof ApiError ? caught.message : "Could not open this workflow.");
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [organizationId, setEdges, setNodes, workflowId]);

  useEffect(() => {
    if (!organizationId) return;
    let active = true;
    api<KnowledgeDocument[]>("/knowledge/documents", { orgId: organizationId })
      .then((rows) => {
        if (active) setDocuments(rows);
      })
      .catch(() => {
        if (active) setDocuments([]);
      });
    api<AnalystDataset[]>("/analyst/datasets", { orgId: organizationId })
      .then((rows) => {
        if (active) setDatasets(rows);
      })
      .catch(() => {
        if (active) setDatasets([]);
      });
    return () => {
      active = false;
    };
  }, [organizationId]);

  useEffect(() => {
    if (!organizationId || !currentId) {
      setRuns([]);
      return;
    }
    let active = true;
    api<WorkflowExecution[]>(`/workflows/${currentId}/executions`, { orgId: organizationId })
      .then((rows) => {
        if (active) setRuns(rows);
      })
      .catch(() => {
        if (active) setRuns([]);
      });
    return () => {
      active = false;
    };
  }, [organizationId, currentId, latest]);

  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((current) =>
        addEdge(
          {
            ...connection,
            sourceHandle: connection.sourceHandle ?? "out",
            label: connection.sourceHandle === "true" ? "Yes" : connection.sourceHandle === "false" ? "No" : undefined,
            style: { stroke: connection.sourceHandle === "false" ? "#1C1C1A" : "#4E6574" },
          },
          current,
        ),
      );
    },
    [setEdges],
  );

  const isValidConnection = useCallback(
    (connection: Connection | Edge) => connectionAllowed(connection, nodes),
    [nodes],
  );

  function onDrop(event: React.DragEvent) {
    event.preventDefault();
    const type = event.dataTransfer.getData("application/vansora-node");
    const item = catalogByType[type];
    if (!item) return;
    const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });
    const id = crypto.randomUUID();
    setNodes((current) =>
      current.concat({
        id,
        type: "workflow",
        position,
        data: { nodeType: type, label: item.label, config: defaultConfig(type) },
      }),
    );
    setSelectedId(id);
  }

  function updateSelected(patch: Partial<WorkflowNodeData>) {
    if (!selectedId) return;
    setNodes((current) =>
      current.map((node) => (node.id === selectedId ? { ...node, data: { ...node.data, ...patch } } : node)),
    );
  }

  function removeSelected() {
    if (!selectedId) return;
    setNodes((current) => current.filter((node) => node.id !== selectedId));
    setEdges((current) => current.filter((edge) => edge.source !== selectedId && edge.target !== selectedId));
    setSelectedId(null);
  }

  async function save() {
    if (!organizationId) return null;
    setSaving(true);
    setError(null);
    try {
      const saved = await api<WorkflowDetail>(currentId ? `/workflows/${currentId}` : "/workflows", {
        method: currentId ? "PATCH" : "POST",
        orgId: organizationId,
        body: JSON.stringify({
          name,
          description: description.trim() || null,
          status,
          nodes: nodes.map((node) => ({
            id: node.id,
            node_type: node.data.nodeType,
            label: node.data.label,
            position_x: node.position.x,
            position_y: node.position.y,
            config: configForSave(node.data.nodeType, node.data.config),
          })),
          edges: edges.map((edge) => ({
            ...(edge.id && UUID_PATTERN.test(edge.id) ? { id: edge.id } : {}),
            source_node_id: edge.source,
            target_node_id: edge.target,
            source_handle: edge.sourceHandle ?? "out",
            target_handle: edge.targetHandle ?? null,
          })),
        }),
      });
      setCurrentId(saved.id);
      setNodes(saved.nodes.map(toNode));
      setEdges(saved.edges.map(toEdge));
      if (workflowId === "new") router.replace(`/workflows/${saved.id}`);
      return saved;
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The workflow could not be saved.");
      return null;
    } finally {
      setSaving(false);
    }
  }

  function onSave(event?: FormEvent) {
    event?.preventDefault();
    void save();
  }

  async function onRun(event?: FormEvent) {
    event?.preventDefault();
    if (!organizationId) return;
    if (status === "paused") {
      setError("Paused workflows do not run. Set the status to draft or active, then save.");
      return;
    }
    if (trigger?.data.nodeType === "manual_trigger" && runText.trim().length < 1) {
      setError("Enter the text this run should use.");
      return;
    }
    if (trigger?.data.nodeType === "document_uploaded" && !documentId) {
      setError("Choose a document for this run.");
      return;
    }
    if (trigger?.data.nodeType === "dataset_uploaded" && !datasetId) {
      setError("Choose a dataset for this run.");
      return;
    }
    setRunning(true);
    const saved = await save();
    if (!saved) {
      setRunning(false);
      return;
    }
    try {
      const execution = await api<WorkflowExecution>(`/workflows/${saved.id}/run`, {
        method: "POST",
        orgId: organizationId,
        body: JSON.stringify({
          text: runText,
          document_id: documentId || null,
          dataset_id: datasetId || null,
        }),
      });
      setLatest(execution);
      if (execution.status === "failed") setError(execution.error_message);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The workflow could not be run.");
    } finally {
      setRunning(false);
    }
  }

  async function removeWorkflow() {
    if (!organizationId || !currentId) return;
    if (!window.confirm("Delete this workflow and its run history?")) return;
    setError(null);
    try {
      await api(`/workflows/${currentId}`, { method: "DELETE", orgId: organizationId });
      router.push("/workflows");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The workflow could not be deleted.");
    }
  }

  const categories = useMemo(() => ["Trigger", "AI", "Logic", "Action"] as const, []);

  if (!organization) {
    return (
      <section className="max-w-lg">
        <h1 className="text-2xl font-semibold">Workflows</h1>
        <p className="mt-2 text-muted">Create an organization before drawing a workflow.</p>
        <Link href="/settings" className="mt-4 inline-block text-sm font-medium">
          Create an organization
        </Link>
      </section>
    );
  }

  return (
    <section>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link href="/workflows" className="text-sm text-muted">
            Workflows
          </Link>
          <h1 className="mt-1 text-2xl font-semibold">Workflow builder</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            Drag a node onto the canvas, connect it, then press Run. Uploading a file does not start a workflow.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className={buttonClass} onClick={onSave} disabled={saving || running}>
            {saving ? "Saving…" : "Save"}
          </button>
          <button type="button" className={buttonClass} onClick={onRun} disabled={saving || running || status === "paused"}>
            {running ? "Running…" : "Run"}
          </button>
          {currentId ? (
            <button type="button" className="rounded-md border border-line px-4 py-2 text-sm" onClick={removeWorkflow}>
              Delete
            </button>
          ) : null}
        </div>
      </div>
      {error ? <p className="mt-4 text-sm text-red-700">{error}</p> : null}
      {loading ? <p className="mt-4 text-sm text-muted">Loading workflow…</p> : null}

      <form className="mt-4 grid gap-3 md:grid-cols-[1fr_180px]" onSubmit={onSave}>
        <label className="block text-sm">
          <span className="text-muted">Name</span>
          <input className={`${fieldClass} mt-1`} value={name} onChange={(event) => setName(event.target.value)} maxLength={160} />
        </label>
        <label className="block text-sm">
          <span className="text-muted">Status</span>
          <select className={`${fieldClass} mt-1`} value={status} onChange={(event) => setStatus(event.target.value as "draft" | "active" | "paused")}>
            <option value="draft">Draft</option>
            <option value="active">Active</option>
            <option value="paused">Paused</option>
          </select>
        </label>
        <label className="block text-sm md:col-span-2">
          <span className="text-muted">Description</span>
          <input className={`${fieldClass} mt-1`} value={description} onChange={(event) => setDescription(event.target.value)} maxLength={2000} />
        </label>
      </form>

      <div className="mt-4 grid gap-3 xl:grid-cols-[220px_minmax(0,1fr)_280px]">
        <aside className="surface-card rounded-lg border border-line p-3">
          <p className="text-xs font-medium tracking-wide text-muted uppercase">Nodes</p>
          {categories.map((category) => (
            <div key={category} className="mt-3">
              <p className="text-xs text-muted">{category}</p>
              <div className="mt-1 grid gap-1">
                {CATALOG.filter((item) => item.category === category).map((item) => (
                  <button
                    key={item.type}
                    type="button"
                    draggable
                    onDragStart={(event) => {
                      event.dataTransfer.setData("application/vansora-node", item.type);
                      event.dataTransfer.effectAllowed = "move";
                    }}
                    className="rounded-md border border-line bg-ivory px-2 py-1.5 text-left text-sm hover:border-steel"
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </aside>

        <div
          className="relative h-[34rem] overflow-hidden rounded-lg border border-line bg-ivory"
          onDragOver={(event) => event.preventDefault()}
          onDrop={onDrop}
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            isValidConnection={isValidConnection}
            nodeTypes={nodeTypes}
            onNodeClick={(_event, node) => setSelectedId(node.id)}
            onPaneClick={() => setSelectedId(null)}
            fitView
            deleteKeyCode={["Backspace", "Delete"]}
            proOptions={{ hideAttribution: false }}
            style={{ background: "var(--ivory)" }}
          >
            <Fit marker={`${currentId ?? "new"}:${nodes.length}`} />
            <MiniMap pannable zoomable nodeColor="#4E6574" maskColor="rgba(245, 244, 240, 0.7)" />
            <Controls showInteractive={false} />
            <Background gap={18} size={1} color="#c5c1b7" />
          </ReactFlow>
        </div>

        <aside className="surface-card h-fit rounded-lg border border-line p-4">
          {selected ? (
            <NodeSettings
              node={selected}
              onLabel={(label) => updateSelected({ label })}
              onConfig={(key, value) =>
                updateSelected({ config: { ...selected.data.config, [key]: value } })
              }
              onRemove={removeSelected}
            />
          ) : (
            <>
              <h2 className="font-medium">Configuration</h2>
              <p className="mt-2 text-sm text-muted">Select a node to edit its name and settings. Yes and No are the two outputs of a logic node.</p>
            </>
          )}
        </aside>
      </div>

      <form className="surface-card mt-4 rounded-lg border border-line p-4" onSubmit={onRun}>
        <h2 className="font-medium">Manual run</h2>
        <p className="mt-1 text-sm text-muted">The run uses the trigger on the canvas. It stops if a step fails.</p>
        {trigger?.data.nodeType === "manual_trigger" ? (
          <label className="mt-3 block text-sm">
            <span className="text-muted">Text</span>
            <textarea className={`${fieldClass} mt-1 min-h-24`} value={runText} onChange={(event) => setRunText(event.target.value)} maxLength={8000} />
          </label>
        ) : null}
        {trigger?.data.nodeType === "document_uploaded" ? (
          <label className="mt-3 block text-sm">
            <span className="text-muted">Document</span>
            <select className={`${fieldClass} mt-1`} value={documentId} onChange={(event) => setDocumentId(event.target.value)}>
              <option value="">Choose a ready document</option>
              {documents.filter((document) => document.status === "ready").map((document) => (
                <option key={document.id} value={document.id}>{document.filename}</option>
              ))}
            </select>
          </label>
        ) : null}
        {trigger?.data.nodeType === "dataset_uploaded" ? (
          <label className="mt-3 block text-sm">
            <span className="text-muted">Dataset</span>
            <select className={`${fieldClass} mt-1`} value={datasetId} onChange={(event) => setDatasetId(event.target.value)}>
              <option value="">Choose a ready dataset</option>
              {datasets.filter((dataset) => dataset.status === "ready").map((dataset) => (
                <option key={dataset.id} value={dataset.id}>{dataset.name}</option>
              ))}
            </select>
          </label>
        ) : null}
        {!trigger ? <p className="mt-3 text-sm text-muted">Add one trigger before running.</p> : null}
      </form>

      {latest ? (
        <article className="surface-card mt-4 rounded-lg border border-line p-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="font-medium">Latest run · {latest.status}</h2>
            <Link href={`/workflows/runs/${latest.id}`} className="text-sm font-medium">
              Open run
            </Link>
          </div>
          <ul className="mt-3 grid gap-2">
            {latest.steps.map((step) => (
              <li key={step.id} className="rounded-md border border-line px-3 py-2 text-sm">
                <span className="font-medium">{step.node_label}</span>
                <span className="text-muted"> · {stepLabel(step.status, step.output_json)} · {durationLabel(step.duration_ms)}</span>
                {step.error_message ? <p className="mt-1 text-red-700">{step.error_message}</p> : null}
                {typeof step.output_json?.text === "string" && step.output_json.text ? (
                  <p className="mt-1 whitespace-pre-wrap text-muted">{step.output_json.text}</p>
                ) : null}
              </li>
            ))}
          </ul>
        </article>
      ) : null}

      {runs.length > 0 ? (
        <article className="mt-4">
          <h2 className="font-medium">History</h2>
          <ul className="mt-2 grid gap-2">
            {runs.slice(0, 6).map((run) => (
              <li key={run.id}>
                <Link href={`/workflows/runs/${run.id}`} className="flex items-center justify-between rounded-md border border-line bg-surface px-3 py-2 text-sm">
                  <span className="capitalize">{run.status}</span>
                  <span className="text-muted">{new Date(run.created_at).toLocaleString()} · {durationLabel(run.duration_ms)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </article>
      ) : null}
    </section>
  );
}

function NodeSettings({
  node,
  onLabel,
  onConfig,
  onRemove,
}: {
  node: FlowNode;
  onLabel: (label: string) => void;
  onConfig: (key: string, value: string | string[]) => void;
  onRemove: () => void;
}) {
  const item = catalogByType[node.data.nodeType];
  const config = node.data.config;
  return (
    <div>
      <p className="text-xs tracking-wide text-muted uppercase">{item?.category}</p>
      <h2 className="mt-1 font-medium">{item?.label}</h2>
      <p className="mt-2 text-sm text-muted">{item?.description}</p>
      <label className="mt-3 block text-sm">
        <span className="text-muted">Name on the canvas</span>
        <input className={`${fieldClass} mt-1`} value={node.data.label} onChange={(event) => onLabel(event.target.value)} maxLength={160} />
      </label>
      {node.data.nodeType === "summarise_text" || node.data.nodeType === "generate_response" ? (
        <TextSetting label="Instruction" value={textValue(config.instruction)} onChange={(value) => onConfig("instruction", value)} />
      ) : null}
      {node.data.nodeType === "analyse_document" ? (
        <TextSetting label="Question" value={textValue(config.question)} onChange={(value) => onConfig("question", value)} />
      ) : null}
      {node.data.nodeType === "extract_information" ? (
        <LinesSetting key={`${node.id}-fields`} label="Fields, one per line" value={listValue(config.fields)} onChange={(value) => onConfig("fields", value)} />
      ) : null}
      {node.data.nodeType === "classify_content" ? (
        <LinesSetting key={`${node.id}-labels`} label="Labels, one per line" value={listValue(config.labels)} onChange={(value) => onConfig("labels", value)} />
      ) : null}
      {node.data.nodeType === "condition" ? (
        <>
          <TextSetting label="Field" value={textValue(config.field)} onChange={(value) => onConfig("field", value)} />
          <OperatorSetting value={textValue(config.operator)} onChange={(value) => onConfig("operator", value)} />
          <TextSetting label="Value" value={textValue(config.value)} onChange={(value) => onConfig("value", value)} />
        </>
      ) : null}
      {node.data.nodeType === "compare_values" ? (
        <>
          <TextSetting label="Left field" value={textValue(config.left_field)} onChange={(value) => onConfig("left_field", value)} />
          <OperatorSetting value={textValue(config.operator)} onChange={(value) => onConfig("operator", value)} />
          <TextSetting label="Right field" value={textValue(config.right_field)} onChange={(value) => onConfig("right_field", value)} />
          <TextSetting label="Or a fixed value" value={textValue(config.right_value)} onChange={(value) => onConfig("right_value", value)} />
        </>
      ) : null}
      {node.data.nodeType === "field_exists" ? (
        <TextSetting label="Field" value={textValue(config.field)} onChange={(value) => onConfig("field", value)} />
      ) : null}
      {node.data.nodeType === "save_result" ? (
        <TextSetting label="Saved name" value={textValue(config.name)} onChange={(value) => onConfig("name", value)} />
      ) : null}
      {node.data.nodeType === "update_status" ? (
        <label className="mt-3 block text-sm">
          <span className="text-muted">New status</span>
          <select className={`${fieldClass} mt-1`} value={textValue(config.status) || "active"} onChange={(event) => onConfig("status", event.target.value)}>
            <option value="draft">Draft</option>
            <option value="active">Active</option>
            <option value="paused">Paused</option>
          </select>
        </label>
      ) : null}
      {node.data.nodeType === "create_notification" ? (
        <>
          <TextSetting label="Title" value={textValue(config.title)} onChange={(value) => onConfig("title", value)} />
          <TextSetting label="Message" value={textValue(config.message)} onChange={(value) => onConfig("message", value)} />
        </>
      ) : null}
      {node.data.nodeType === "generate_report" ? (
        <TextSetting label="Title" value={textValue(config.title)} onChange={(value) => onConfig("title", value)} />
      ) : null}
      <button type="button" className="mt-4 text-sm text-muted" onClick={onRemove}>
        Remove node
      </button>
    </div>
  );
}

function TextSetting({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="mt-3 block text-sm">
      <span className="text-muted">{label}</span>
      <input className={`${fieldClass} mt-1`} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function OperatorSetting({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <label className="mt-3 block text-sm">
      <span className="text-muted">Comparison</span>
      <select className={`${fieldClass} mt-1`} value={value || "eq"} onChange={(event) => onChange(event.target.value)}>
        {OPERATORS.map(([operator, label]) => (
          <option key={operator} value={operator}>{label}</option>
        ))}
      </select>
    </label>
  );
}

function LinesSetting({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string[];
  onChange: (value: string[]) => void;
}) {
  const [text, setText] = useState(value.join("\n"));
  return (
    <label className="mt-3 block text-sm">
      <span className="text-muted">{label}</span>
      <textarea
        className={`${fieldClass} mt-1 min-h-24`}
        value={text}
        onChange={(event) => {
          const next = event.target.value;
          setText(next);
          onChange(next.split(/\r?\n/).map((item) => item.trim()).filter(Boolean));
        }}
      />
    </label>
  );
}

const CanvasNode = memo(function CanvasNode({ data, selected }: NodeProps<FlowNode>) {
  const item = catalogByType[data.nodeType];
  const logic = item?.logic;
  return (
    <div className={`min-w-40 rounded-md border border-l-4 bg-surface px-3 py-2 shadow-sm ${selected ? "border-steel" : "border-line"} ${item?.category === "AI" ? "border-l-ink" : "border-l-steel"}`}>
      {item?.category !== "Trigger" ? <Handle type="target" position={Position.Left} className="!h-2.5 !w-2.5 !border-0 !bg-ink" /> : null}
      <p className="text-[10px] tracking-wide text-muted uppercase">{item?.category}</p>
      <p className="max-w-44 truncate text-sm font-medium">{data.label}</p>
      {logic ? <p className="mt-1 text-[10px] text-muted">Yes and No</p> : null}
      {logic ? (
        <>
          <Handle id="true" type="source" position={Position.Right} style={{ top: 18 }} className="!h-2.5 !w-2.5 !border-0 !bg-steel" />
          <Handle id="false" type="source" position={Position.Right} style={{ top: 42 }} className="!h-2.5 !w-2.5 !border-0 !bg-ink" />
        </>
      ) : (
        <Handle id="out" type="source" position={Position.Right} className="!h-2.5 !w-2.5 !border-0 !bg-steel" />
      )}
    </div>
  );
});

const nodeTypes = { workflow: CanvasNode };

function Fit({ marker }: { marker: string }) {
  const { fitView } = useReactFlow();
  useEffect(() => {
    const timer = window.setTimeout(() => fitView({ padding: 0.2 }), 40);
    return () => window.clearTimeout(timer);
  }, [fitView, marker]);
  return null;
}

function blankNode(): FlowNode {
  return {
    id: crypto.randomUUID(),
    type: "workflow",
    position: { x: 80, y: 140 },
    data: { nodeType: "manual_trigger", label: "Manual trigger", config: {} },
  };
}

function toNode(node: WorkflowDetail["nodes"][number]): FlowNode {
  const config: Record<string, string | string[]> = {};
  for (const [key, value] of Object.entries(node.config || {})) {
    if (Array.isArray(value)) config[key] = value.map(String);
    else if (typeof value === "string") config[key] = value;
  }
  return {
    id: node.id,
    type: "workflow",
    position: { x: node.position_x, y: node.position_y },
    data: { nodeType: node.node_type, label: node.label, config },
  };
}

function toEdge(edge: WorkflowDetail["edges"][number]): Edge {
  return {
    id: edge.id,
    source: edge.source_node_id,
    target: edge.target_node_id,
    sourceHandle: edge.source_handle ?? "out",
    targetHandle: edge.target_handle ?? undefined,
    label: edge.source_handle === "true" ? "Yes" : edge.source_handle === "false" ? "No" : undefined,
    style: { stroke: edge.source_handle === "false" ? "#1C1C1A" : "#4E6574" },
  };
}

function connectionAllowed(connection: Connection | Edge, nodes: FlowNode[]) {
  if (!connection.source || !connection.target || connection.source === connection.target) return false;
  const source = nodes.find((node) => node.id === connection.source);
  const target = nodes.find((node) => node.id === connection.target);
  if (!source || !target) return false;
  const sourceItem = catalogByType[source.data.nodeType];
  const targetItem = catalogByType[target.data.nodeType];
  if (!sourceItem || !targetItem || targetItem.category === "Trigger") return false;
  const handle = connection.sourceHandle || "out";
  if (sourceItem.logic) return handle === "true" || handle === "false";
  return handle === "out";
}
