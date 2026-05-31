import React from "react";

type ZonePageLayoutProps = {
  mapSlot: React.ReactNode;
  detailSlot: React.ReactNode;
};

export default function ZonePageLayout({
  mapSlot,
  detailSlot,
}: ZonePageLayoutProps) {
  return (
    <div className="flex flex-col lg:flex-row h-full w-full">
      {/* Map Section */}
      <div className="h-[50vh] lg:h-full lg:flex-1 relative">{mapSlot}</div>
      {/* Detail Panel Section */}
      <div className="h-[50vh] lg:h-full lg:w-96 overflow-y-auto border-t lg:border-t-0 lg:border-l border-slate-200 bg-white">
        {detailSlot}
      </div>
    </div>
  );
}
