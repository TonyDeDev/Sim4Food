"use client";

import { use } from "react";
import { notFound } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { WorkspaceTabs } from "@/components/shell/WorkspaceTabs";

export default function BusinessLayout(props: LayoutProps<"/businesses/[id]">) {
  const { id } = use(props.params);
  const { businesses } = useAuth();
  const business = businesses.find((biz) => biz.id === id);

  if (!business) {
    notFound();
  }

  return (
    <div className="mx-auto max-w-[1200px]">
      <h1 className="mb-6 font-serif text-heading-sm font-normal text-press-black">{business.name}</h1>
      <WorkspaceTabs businessId={id} />
      {props.children}
    </div>
  );
}
