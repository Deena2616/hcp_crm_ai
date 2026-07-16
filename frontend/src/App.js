import React, { useEffect } from "react";
import { useDispatch } from "react-redux";
import { fetchHcps } from "./redux/slices/hcpsSlice";
import Header from "./components/Header";
import LogInteractionScreen from "./components/LogInteractionScreen";

function App() {
  const dispatch = useDispatch();

  useEffect(() => {
    dispatch(fetchHcps());
  }, [dispatch]);

  return (
    <div className="app-shell">
      <Header />
      <main className="app-main">
        <LogInteractionScreen />
      </main>
    </div>
  );
}

export default App;
