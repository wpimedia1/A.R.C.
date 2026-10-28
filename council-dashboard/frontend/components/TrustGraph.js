"use client";

import { useEffect, useRef } from "react";
import * as d3 from "d3";

const COLORS = ["#4da3ff", "#ffb020", "#2dd4a8", "#ff4d5e"];

export default function TrustGraph({ clusters, counters }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!clusters || !ref.current) return;
    const { agents, labels } = clusters;
    const nodes = agents.map((id, i) => ({ id, group: labels[i] }));
    const links = (counters || [])
      .filter((c) => agents.includes(c.from) && agents.includes(c.target))
      .map((c) => ({ source: c.from, target: c.target }));

    const el = ref.current;
    el.innerHTML = "";
    const width = el.clientWidth || 520;
    const height = 300;
    const svg = d3.select(el).append("svg")
      .attr("width", width).attr("height", height);

    const sim = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links).id((d) => d.id).distance(110))
      .force("charge", d3.forceManyBody().strength(-260))
      .force("center", d3.forceCenter(width / 2, height / 2));

    const link = svg.append("g")
      .selectAll("line").data(links).join("line")
      .attr("class", "xlink")
      .attr("stroke", "#ff4d5e").attr("stroke-opacity", 0.55);

    const node = svg.append("g")
      .selectAll("g").data(nodes).join("g")
      .call(d3.drag()
        .on("start", (e, d) => {
          if (!e.active) sim.alphaTarget(0.3).restart();
          d.fx = d.x; d.fy = d.y;
        })
        .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
        .on("end", (e, d) => {
          if (!e.active) sim.alphaTarget(0);
          d.fx = null; d.fy = null;
        }));

    node.append("circle")
      .attr("r", 20)
      .attr("fill", (d) => COLORS[d.group % COLORS.length])
      .attr("fill-opacity", 0.25)
      .attr("stroke", (d) => COLORS[d.group % COLORS.length])
      .attr("stroke-width", 2);

    node.append("text")
      .text((d) => d.id.replace(/_/g, " ").slice(0, 12))
      .attr("text-anchor", "middle").attr("dy", 4)
      .attr("fill", "#e8edf5").attr("font-size", 10)
      .attr("font-family", "monospace");

    sim.on("tick", () => {
      link.attr("x1", (d) => d.source.x).attr("y1", (d) => d.source.y)
        .attr("x2", (d) => d.target.x).attr("y2", (d) => d.target.y);
      node.attr("transform", (d) => `translate(${d.x},${d.y})`);
    });

    return () => sim.stop();
  }, [clusters, counters]);

  if (!clusters) return <p className="mono">Awaiting Round 2 clustering…</p>;
  return <div ref={ref} style={{ width: "100%" }} />;
}
