export class ApiError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

export function errorFromBody(body: unknown, status: number): ApiError {
  const record = body as { error?: { code?: string; message?: string } } | null;
  return new ApiError(
    record?.error?.code ?? "request_failed",
    record?.error?.message ?? "Request failed.",
    status,
  );
}
