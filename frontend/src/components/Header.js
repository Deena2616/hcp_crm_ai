import React from "react";
import "./Header.css";

export default function Header() {
  return (
    <>
      {/* <div className="app-header__accent" /> */}
      <header className="app-header">
        <span className="app-header__title">AI-First CRM</span>
        <span className="app-header__sep">·</span>
        <span className="app-header__module">HCP Module</span>
      </header>
    </>
  );
}
