import React from "react";
import { useSelector } from "react-redux";

export default function HcpAutocomplete({ value, onChange, id = "hcp-name-list" }) {
  const hcps = useSelector((state) => state.hcps.items);

  return (
    <>
      <input
        list={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Search or select HCP..."
        required
      />
      <datalist id={id}>
        {hcps.map((h) => (
          <option key={h.id} value={h.name} />
        ))}
      </datalist>
    </>
  );
}
