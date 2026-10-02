from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

from .common import graph_record


class MMPCAdapterError(RuntimeError):
    pass


class MMPCAdapter:
    def __init__(self, rscript: str, library: Path | None, required_version: str, *, fixture: bool = False):
        self.rscript = rscript
        self.library = library
        self.required_version = required_version
        self.fixture = fixture
        if not fixture:
            self._verify_runtime()

    @staticmethod
    def _normalize_version(value: str) -> str:
        return value.strip().replace("-", ".")

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self.library is not None:
            env["R_LIBS_USER"] = str(self.library)
        return env

    def _verify_runtime(self) -> None:
        if shutil.which(self.rscript) is None:
            raise MMPCAdapterError(f"Rscript missing: {self.rscript}")
        probe = subprocess.run([self.rscript, "-e", "cat(as.character(packageVersion('bnlearn')))"] , env=self._env(), capture_output=True, text=True, timeout=60)
        observed = probe.stdout.strip()
        if probe.returncode != 0 or self._normalize_version(observed) != self._normalize_version(self.required_version):
            raise MMPCAdapterError(f"bnlearn version mismatch: {observed!r} != {self.required_version!r}")

    def run(self, nodes: list[str], values: Any, parameters: dict[str, Any]) -> tuple[dict[str, Any], float]:
        if self.fixture:
            return graph_record(nodes, [], [nodes[:2]] if len(nodes) >= 2 else [], graph_type="skeleton"), 0.0
        started = time.perf_counter()
        matrix = np.asarray(values, dtype=float)
        with tempfile.TemporaryDirectory(prefix="p1v3_mmpc_") as tmp:
            data_path = Path(tmp) / "data.tsv"
            out_path = Path(tmp) / "result.txt"
            np.savetxt(data_path, matrix, delimiter="\t")
            alpha = float(parameters["alpha"])
            max_sx = parameters.get("max_sx")
            max_sx_r = "NULL" if max_sx is None else str(int(max_sx))
            undirected = "TRUE" if bool(parameters.get("undirected", True)) else "FALSE"
            test = str(parameters.get("test", "zf"))
            r_code = "\n".join([
                "args <- commandArgs(trailingOnly=TRUE)",
                "d <- as.data.frame(read.table(args[[1]], header=FALSE, sep='\\t', check.names=FALSE))",
                "names(d) <- paste0('X', sprintf('%03d', seq_len(ncol(d))-1))",
                f"fit <- bnlearn::mmpc(d, test={test!r}, alpha={alpha!r}, max.sx={max_sx_r}, undirected={undirected})",
                "a <- bnlearn::amat(fit)",
                "edges <- character(0)",
                "for (i in seq_len(nrow(a))) for (j in seq_len(ncol(a))) if (i < j && a[i,j] != 0) edges <- c(edges, paste0(colnames(a)[i], '|', colnames(a)[j]))",
                "writeLines(c(paste(colnames(a), collapse='|'), edges), args[[2]])",
            ])
            # R parses backslashes in Windows command arguments as escapes;
            # use canonical forward-slash paths for deterministic subprocess I/O.
            proc = subprocess.run([self.rscript, "-e", r_code, data_path.as_posix(), out_path.as_posix()], env=self._env(), capture_output=True, text=True, timeout=300)
            if proc.returncode != 0:
                raise MMPCAdapterError(proc.stderr.strip() or "mmpc failed")
            lines = out_path.read_text(encoding="utf-8").splitlines()
            if not lines:
                raise MMPCAdapterError("mmpc returned empty output")
            observed_nodes = lines[0].split("|")
            edges = [line.split("|") for line in lines[1:] if line]
            if observed_nodes != nodes:
                raise MMPCAdapterError("mmpc changed node universe")
            return graph_record(nodes, [], edges, graph_type="skeleton"), time.perf_counter() - started
