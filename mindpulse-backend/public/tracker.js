/*
  MindPulse tracker
  ------------------
  Drop this on any test page (after the existing quiz script, or before —
  order doesn't matter since it only defines functions) to persist results
  to the Flask backend.

  Usage from inside a test's showResult():
      saveResult({
        test_type: "mood",     // one of: mood, focus, memory, decision,
                                // personality, iq, color, sequence, games
        score: moodScore,
        max_score: 45,         // optional but recommended
        label: mood,           // the human-readable result label you show
        time_taken_sec: totalTime  // optional
      });

  Fails silently (console.warn only) so a backend outage never breaks the
  quiz itself.
*/

function getMindpulseUserId() {
  let uid = localStorage.getItem("mindpulse_uid");
  if (!uid) {
    uid = "u_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 10);
    localStorage.setItem("mindpulse_uid", uid);
  }
  return uid;
}

async function saveResult({ test_type, score, max_score = null, label = null, time_taken_sec = null }) {
  const payload = {
    user_id: getMindpulseUserId(),
    test_type,
    score,
    max_score,
    label,
    time_taken_sec,
  };
  try {
    const res = await fetch("/api/results", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      console.warn("MindPulse: result not saved", await res.text());
    }
  } catch (err) {
    console.warn("MindPulse: could not reach backend, result not saved", err);
  }
}
