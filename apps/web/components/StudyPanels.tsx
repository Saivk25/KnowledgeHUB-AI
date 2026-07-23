"use client";

/**
 * Milestone 10 (Study Workflows): Quiz me, Flashcards, and Viva mode
 * panels. Shared between the Document detail page and the Concept detail
 * page (both resolve a `target` of exactly one of `resourceId`/
 * `conceptId`), the same way each page already embeds its own Summarize
 * panel (Milestone 9) inline rather than through a shared component --
 * these three are pulled into one shared component specifically because
 * three intents x two pages would otherwise triplicate turn-taking state
 * machines (quiz generate/grade, viva start/continue) that must stay
 * byte-for-byte identical on both pages.
 */
import { useState } from "react";
import {
  api,
  ApiError,
  CitationOut,
  FlashcardsResultOut,
  QuizGradedQuestionOut,
  QuizQuestionOut,
  QuizResultOut,
  VivaResultOut,
} from "@/lib/api";
import CitationPill from "@/components/CitationPill";

export interface StudyTarget {
  resourceId?: string;
  conceptId?: string;
}

function useConversation() {
  // Every intent request (Milestone 9's shared envelope) is dispatched
  // through a conversation -- these panels create one lazily on first use
  // and reuse it for the rest of the turn-taking flow (grading/continuing).
  const [conversationId, setConversationId] = useState<string | null>(null);
  const ensure = async () => {
    if (conversationId) return conversationId;
    const conv = await api.createConversation();
    setConversationId(conv.id);
    return conv.id;
  };
  return ensure;
}

// -- Quiz me -----------------------------------------------------------

export function QuizPanel({ target }: { target: StudyTarget }) {
  const ensureConversation = useConversation();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quiz, setQuiz] = useState<QuizResultOut | null>(null);
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [activeCitation, setActiveCitation] = useState<CitationOut | null>(null);

  const onGenerate = async () => {
    setLoading(true);
    setError(null);
    setQuiz(null);
    setAnswers({});
    try {
      const convId = await ensureConversation();
      const res = await api.sendIntent(convId, { intent: "QUIZ", ...target, questionCount: 5 });
      if (res.status !== "OK") {
        setError("Couldn't find enough evidence to generate a quiz.");
        return;
      }
      setQuiz(res.result as QuizResultOut);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't generate a quiz.");
    } finally {
      setLoading(false);
    }
  };

  const onSubmit = async () => {
    if (!quiz) return;
    setLoading(true);
    setError(null);
    try {
      const convId = await ensureConversation();
      const quizAnswers = Object.entries(answers).map(([questionNumber, selectedChoice]) => ({
        questionNumber: Number(questionNumber),
        selectedChoice,
      }));
      const res = await api.sendIntent(convId, { intent: "QUIZ", quizId: quiz.quizId, quizAnswers });
      if (res.status !== "OK") {
        setError("Couldn't grade this quiz.");
        return;
      }
      setQuiz(res.result as QuizResultOut);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't grade this quiz.");
    } finally {
      setLoading(false);
    }
  };

  const allAnswered =
    quiz?.questions != null && quiz.questions.every((q) => answers[q.questionNumber] !== undefined);

  return (
    <div className="rounded-lg border border-edge bg-surface px-4 py-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Quiz me</p>
        <button
          onClick={onGenerate}
          disabled={loading}
          className="rounded-lg border border-indigo px-3 py-1.5 text-xs font-medium text-indigo hover:bg-indigo/5 disabled:opacity-50"
        >
          {loading ? "Working…" : quiz ? "New quiz" : "Generate a quiz"}
        </button>
      </div>
      {error && <p className="mt-2 text-xs text-rose-700">{error}</p>}

      {quiz?.status === "AWAITING_ANSWERS" && quiz.questions && (
        <div className="mt-3 space-y-4">
          {quiz.questions.map((q: QuizQuestionOut) => (
            <div key={q.questionNumber} className="rounded-lg border border-edge px-3 py-2">
              <p className="text-sm font-medium text-ink">
                {q.questionNumber}. {q.prompt}
              </p>
              <div className="mt-2 space-y-1">
                {q.choices.map((choice, idx) => (
                  <label key={idx} className="flex items-center gap-2 text-sm text-slate-600">
                    <input
                      type="radio"
                      name={`quiz-q${q.questionNumber}`}
                      checked={answers[q.questionNumber] === idx}
                      onChange={() => setAnswers((a) => ({ ...a, [q.questionNumber]: idx }))}
                    />
                    {choice}
                  </label>
                ))}
              </div>
            </div>
          ))}
          <button
            onClick={onSubmit}
            disabled={!allAnswered || loading}
            className="rounded-lg bg-indigo px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo/90 disabled:opacity-50"
          >
            {loading ? "Grading…" : "Submit answers"}
          </button>
        </div>
      )}

      {quiz?.status === "GRADED" && quiz.gradedQuestions && (
        <div className="mt-3 space-y-3">
          <p className="text-sm font-medium text-ink">
            Score: {Math.round((quiz.score || 0) * 100)}% ({quiz.gradedQuestions.filter((q) => q.isCorrect).length}/
            {quiz.gradedQuestions.length})
          </p>
          {quiz.gradedQuestions.map((q: QuizGradedQuestionOut) => (
            <div
              key={q.questionNumber}
              className={`rounded-lg border px-3 py-2 ${
                q.isCorrect ? "border-emerald/30 bg-emerald/5" : "border-rose/30 bg-rose/5"
              }`}
            >
              <p className="text-sm font-medium text-ink">
                {q.questionNumber}. {q.prompt}
              </p>
              <p className="mt-1 text-xs text-slate-600">
                Your answer: {q.choices[q.selectedChoice] ?? "(none)"} {q.isCorrect ? "✓" : "✗"}
              </p>
              {!q.isCorrect && (
                <p className="mt-1 text-xs text-slate-600">Correct answer: {q.choices[q.correctChoice]}</p>
              )}
              <div className="mt-1.5">
                <CitationPill citation={q.citation} onOpen={setActiveCitation} />
              </div>
            </div>
          ))}
        </div>
      )}
      {activeCitation && (
        <p className="mt-2 text-xs text-slate-400">
          Source: {activeCitation.documentFilename} · p.{activeCitation.pageNumber} — {activeCitation.excerpt}
        </p>
      )}
    </div>
  );
}

// -- Flashcards ----------------------------------------------------------

export function FlashcardsPanel({ target }: { target: StudyTarget }) {
  const ensureConversation = useConversation();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cards, setCards] = useState<FlashcardsResultOut | null>(null);
  const [flipped, setFlipped] = useState<Record<number, boolean>>({});

  const onGenerate = async () => {
    setLoading(true);
    setError(null);
    setFlipped({});
    try {
      const convId = await ensureConversation();
      const res = await api.sendIntent(convId, { intent: "FLASHCARDS", ...target });
      if (res.status !== "OK") {
        setError("Couldn't find enough evidence to generate flashcards.");
        return;
      }
      setCards(res.result as FlashcardsResultOut);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't generate flashcards.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-lg border border-edge bg-surface px-4 py-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Flashcards</p>
        <button
          onClick={onGenerate}
          disabled={loading}
          className="rounded-lg border border-indigo px-3 py-1.5 text-xs font-medium text-indigo hover:bg-indigo/5 disabled:opacity-50"
        >
          {loading ? "Working…" : cards ? "New set" : "Generate flashcards"}
        </button>
      </div>
      {error && <p className="mt-2 text-xs text-rose-700">{error}</p>}
      {cards && (
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {cards.cards.map((card, idx) => (
            <button
              key={idx}
              onClick={() => setFlipped((f) => ({ ...f, [idx]: !f[idx] }))}
              className="rounded-lg border border-edge px-3 py-3 text-left text-sm hover:bg-canvas"
            >
              <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
                {flipped[idx] ? "Back" : "Front"}
              </p>
              <p className="mt-1 text-ink">{flipped[idx] ? card.back : card.front}</p>
              <p className="mt-2 text-xs text-slate-400">
                p.{card.citation.pageNumber} · tap to {flipped[idx] ? "see front" : "reveal"}
              </p>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// -- Viva mode -----------------------------------------------------------

export function VivaPanel({ target }: { target: StudyTarget }) {
  const ensureConversation = useConversation();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<VivaResultOut | null>(null);
  const [answer, setAnswer] = useState("");

  const onStart = async () => {
    setLoading(true);
    setError(null);
    setAnswer("");
    try {
      const convId = await ensureConversation();
      const res = await api.sendIntent(convId, { intent: "VIVA", ...target });
      if (res.status !== "OK") {
        setError("Couldn't find enough evidence to start a viva.");
        return;
      }
      setSession(res.result as VivaResultOut);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't start a viva.");
    } finally {
      setLoading(false);
    }
  };

  const onAnswer = async () => {
    if (!session) return;
    setLoading(true);
    setError(null);
    try {
      const convId = await ensureConversation();
      const res = await api.sendIntent(convId, {
        intent: "VIVA",
        sessionId: session.sessionId,
        vivaAnswer: answer,
      });
      if (res.status !== "OK") {
        setError("Couldn't continue this viva.");
        return;
      }
      setSession(res.result as VivaResultOut);
      setAnswer("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't continue this viva.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-lg border border-edge bg-surface px-4 py-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Viva mode</p>
        {!session || session.isComplete ? (
          <button
            onClick={onStart}
            disabled={loading}
            className="rounded-lg border border-indigo px-3 py-1.5 text-xs font-medium text-indigo hover:bg-indigo/5 disabled:opacity-50"
          >
            {loading ? "Working…" : session ? "Start again" : "Start a viva"}
          </button>
        ) : null}
      </div>
      {error && <p className="mt-2 text-xs text-rose-700">{error}</p>}

      {session && (
        <div className="mt-3 space-y-3">
          {session.previousEvaluation && (
            <div
              className={`rounded-lg border px-3 py-2 text-sm ${
                session.previousEvaluation.verdict === "correct"
                  ? "border-emerald/30 bg-emerald/5 text-emerald-700"
                  : session.previousEvaluation.verdict === "partial"
                  ? "border-amber/30 bg-amber/5 text-amber-700"
                  : "border-rose/30 bg-rose/5 text-rose-700"
              }`}
            >
              <p className="font-medium capitalize">{session.previousEvaluation.verdict}</p>
              <p className="mt-1 text-xs">{session.previousEvaluation.feedback}</p>
            </div>
          )}

          {!session.isComplete && session.nextQuestion && (
            <div>
              <p className="text-sm font-medium text-ink">
                Turn {session.turnNumber}: {session.nextQuestion}
              </p>
              <textarea
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                rows={3}
                className="mt-2 w-full rounded-lg border border-edge bg-surface px-3 py-2 text-sm text-ink"
                placeholder="Your answer…"
              />
              <button
                onClick={onAnswer}
                disabled={loading || !answer.trim()}
                className="mt-2 rounded-lg bg-indigo px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo/90 disabled:opacity-50"
              >
                {loading ? "Grading…" : "Submit answer"}
              </button>
            </div>
          )}

          {session.isComplete && (
            <p className="text-sm text-slate-600">Viva complete — {session.turnNumber} question(s) asked.</p>
          )}
        </div>
      )}
    </div>
  );
}
