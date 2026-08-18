"use client";

/**
 * Who else is in this family archive.
 *
 * The API, the typed client and the proxy allowlist have all supported this for
 * a while — `fetchFamilyMembers`, `updateMemberRole` and `removeMember` existed
 * with zero callers — so an owner could not see who had access to their
 * family's memories anywhere in the product.
 *
 * Read-only on purpose. Core has no invitation lifecycle, so there is nothing
 * honest to put behind an "add member" button; and changing a role or removing
 * somebody is a destructive act on another person's access that deserves its
 * own confirmation design rather than being slipped into a layout pass. Both
 * are recorded in the audit as available-but-not-surfaced instead of being
 * half-built here.
 */

import { useCallback } from "react";
import { PersonAvatar } from "@/components/ui/person-avatar";
import { useMuraI18n } from "@/lib/i18n";
import { fetchFamilyMembers, type FamilyRole, type MemberView } from "@/lib/mura/core-api";
import { useArchiveResource } from "@/lib/mura/use-archive";
import { useMuraSession } from "@/lib/mura/session-provider";

const ROLE_KEY: Record<FamilyRole, "roleOwner" | "roleEditor" | "roleViewer"> = {
  owner: "roleOwner",
  editor: "roleEditor",
  viewer: "roleViewer",
};

export function MembersSection() {
  const { t } = useMuraI18n();
  const { auth } = useMuraSession();
  const load = useCallback(
    (familyId: string, signal: AbortSignal) => fetchFamilyMembers(familyId, signal),
    [],
  );
  const members = useArchiveResource<MemberView[]>(load);

  if (members.status === "loading") {
    return <p className="text-meta text-muted">{t("membersLoading")}</p>;
  }
  // A viewer may not be allowed to read the member list. That is a real answer,
  // not an outage, and saying the service failed would be false.
  if (members.status === "forbidden") {
    return <p className="text-meta text-muted">{t("membersForbidden")}</p>;
  }
  if (!members.data) return null;

  const me = auth.status === "authenticated" ? auth.user.userId : null;

  return (
    <ul className="space-y-2.5">
      {members.data.map((member) => (
        <li key={member.user_id} className="flex items-center gap-3">
          {/*
            An account is not an archive Person, so this avatar is keyed by
            `user_id` and never by a `person_id`. It is a coloured disc for a
            login, not a face in the family tree.
          */}
          <PersonAvatar
            personId={member.user_id}
            displayName={member.display_name ?? "?"}
            size={32}
          />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-body font-medium">
              {/* `user_a78b1a9c…` is an internal identifier, not a name. When
                  the provider supplies neither a display name nor an email
                  there is nothing to call somebody, and saying so plainly beats
                  printing a developer-facing id at their family. */}
              {member.display_name ?? t("memberUnnamed")}
              {member.user_id === me && (
                <span className="ml-1.5 text-meta font-normal text-muted">{t("memberYou")}</span>
              )}
            </span>
          </span>
          <span className="shrink-0 text-meta text-muted">{t(ROLE_KEY[member.role])}</span>
        </li>
      ))}
      <li className="pt-1 text-meta leading-relaxed text-muted">{t("membersNoInvite")}</li>
    </ul>
  );
}
