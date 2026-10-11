"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button, ButtonLink, PageHeader, Panel, ResultsFooter } from "@/components/ui";
import { AccountsPanel } from "@/components/profile/AccountsPanel";
import { GoalsPanel } from "@/components/profile/GoalsPanel";
import { HouseholdPanel } from "@/components/profile/HouseholdPanel";
import { ProfileSkeleton } from "@/components/profile/ProfileSkeleton";
import { TaxPicture } from "@/components/profile/TaxPicture";
import styles from "@/components/profile/Profile.module.css";
import { useApp } from "@/lib/state";

export default function ProfilePage() {
  const { state, actions } = useApp();
  const router = useRouter();
  const { profile } = state;
  // Bumped to run the bootstrap again ("Try again").
  const [attempt, setAttempt] = useState(0);
  const [failedAttempt, setFailedAttempt] = useState(-1);
  const failed = failedAttempt === attempt;

  // Make sure there is a profile: in demo mode that loads the sample documents and builds the
  // household, so this screen works when it is opened directly.
  useEffect(() => {
    let current = true;
    // One tick of delay: the saved demo-mode setting is applied just after this screen first
    // renders, and `ensureProfile` should see it.
    const timer = window.setTimeout(() => {
      void actions.ensureProfile().then((ok) => {
        if (current && !ok) setFailedAttempt(attempt);
      });
    }, 0);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [actions, attempt]);

  const hasDocs = state.docs.some((d) => d.status === "ready");
  // The household could not be built from documents we do have, and not because numbers are missing.
  const showError = failed && hasDocs && state.missing.length === 0 && !!state.error;

  useEffect(() => {
    if (!failed || showError) return;
    // Missing numbers are fixed on Review; with nothing uploaded there is nothing to fix.
    router.replace(state.missing.length > 0 ? "/review" : "/");
  }, [failed, showError, state.missing.length, router]);

  return (
    <>
      <PageHeader
        title="Household profile"
        subtitle="Built from your documents and your answers. Anything estimated is labeled."
        actions={
          profile ? (
            <ButtonLink href="/forecast" arrow>
              See your income forecast
            </ButtonLink>
          ) : (
            <Button arrow disabled>
              See your income forecast
            </Button>
          )
        }
      />

      {showError ? (
        <Panel className={styles.failed} role="alert">
          <h2>We could not build your profile</h2>
          <p>{state.error}</p>
          <Button onClick={() => setAttempt((n) => n + 1)}>Try again</Button>
        </Panel>
      ) : profile ? (
        <>
          <div className={styles.summary}>
            <AccountsPanel profile={profile} />
            <GoalsPanel profile={profile} />
            <HouseholdPanel profile={profile} />
          </div>
          <TaxPicture profile={profile} />
        </>
      ) : (
        <ProfileSkeleton />
      )}

      <ResultsFooter />
    </>
  );
}
