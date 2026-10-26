import { ApiProblem, NetworkProblem } from "./client";

export function errorMessage(error: unknown): string {
  if (error instanceof ApiProblem || error instanceof NetworkProblem) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Something went wrong.";
}

export function errorRequestId(error: unknown): string | undefined {
  return error instanceof ApiProblem && error.requestId
    ? error.requestId
    : undefined;
}
