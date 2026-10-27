import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Workspace } from "./Workspace.tsx";

const root = createRoot(document.getElementById("root")!);
if (
  location.pathname === "/viewer" ||
  document
    .querySelector('meta[name="inside-game-surface"]')
    ?.getAttribute("content") === "viewer"
) {
  Promise.all([
    import("./App.tsx"),
    import("./styles.css"),
    import("./data/api-repository.ts"),
    import("./data/memory-repository.ts"),
  ]).then(
    ([{ App }, , { ApiEpisodeRepository }, { MemoryEpisodeRepository }]) =>
      root.render(
        <StrictMode>
          <App
            repository={new MemoryEpisodeRepository(new ApiEpisodeRepository())}
          />
        </StrictMode>,
      ),
  );
} else
  root.render(
    <StrictMode>
      <Workspace />
    </StrictMode>,
  );
