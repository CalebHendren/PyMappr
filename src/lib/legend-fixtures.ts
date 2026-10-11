// Loads the PyMappr reference cases in fixtures/legend (written by
// scripts/reference_legend.py) for the tests.
import beetles from "./fixtures/beetles-standard.pymappr?raw";
import birds from "./fixtures/hornbills-orchids.pymappr?raw";
import type { ProjectState } from "./model";
import type { PointFilter } from "./symbology";

const SOURCES: Record<string, ProjectState> = {
  "beetles-standard": JSON.parse(beetles).state,
  "hornbills-orchids": JSON.parse(birds).state,
};

export type ReferenceCase = {
  name: string;
  state: ProjectState;
  filter: PointFilter | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  [key: string]: any;
};

const files = import.meta.glob("./fixtures/legend/*.json", { eager: true, import: "default" });

/** Every reference case, with each dataset's rows put back. */
export function referenceCases(): ReferenceCase[] {
  return Object.values(files).map((raw) => {
    const data = structuredClone(raw) as ReferenceCase;
    for (const entry of data.state.datasets as (ProjectState["datasets"][number] & { rowsFrom?: string })[]) {
      if (entry.rowsFrom) {
        const [file, index] = entry.rowsFrom.split("#");
        entry.rows = structuredClone(SOURCES[file].datasets[Number(index)].rows);
        delete entry.rowsFrom;
      }
    }
    return data;
  });
}
