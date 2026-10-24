import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App.tsx";
import { ApiEpisodeRepository } from "./data/api-repository.ts";
import { MemoryEpisodeRepository } from "./data/memory-repository.ts";
import "./styles.css";

const repository = new MemoryEpisodeRepository(new ApiEpisodeRepository());
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App repository={repository} />
  </StrictMode>,
);
