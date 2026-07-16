import React from "react";
import StructuredForm from "./StructuredForm";
import ChatInterface from "./ChatInterface";
import InteractionHistory from "./InteractionHistory";
import "./LogInteractionScreen.css";

export default function LogInteractionScreen() {
  return (
    <div className="log-screen">
      <div className="log-screen__panels">
        <StructuredForm />
        <ChatInterface />
      </div>
      <InteractionHistory />
    </div>
  );
}
