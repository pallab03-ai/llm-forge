import { Inbox } from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";

type ActivityItem = {
  id: string;
  title: string;
  detail?: string;
  timestamp?: string;
};

type ActivityTimelineProps = {
  items?: ActivityItem[];
};

export function ActivityTimeline({ items = [] }: ActivityTimelineProps) {
  if (items.length === 0) {
    return (
      <EmptyState
        icon={<Inbox className="h-6 w-6" aria-hidden />}
        title="No recent activity"
        description="Once you upload a dataset, start a training job, or deploy a model, the latest events will show up here."
      />
    );
  }

  return (
    <ol className="space-y-3" aria-label="Recent activity">
      {items.map((item) => (
        <li
          key={item.id}
          className="flex items-start gap-3 rounded-md border bg-card/40 p-3"
        >
          <span className="mt-1.5 h-2 w-2 flex-shrink-0 rounded-full bg-primary" aria-hidden />
          <div className="min-w-0 flex-1 space-y-0.5">
            <p className="text-sm font-medium leading-none">{item.title}</p>
            {item.detail ? <p className="text-xs text-muted-foreground">{item.detail}</p> : null}
          </div>
          {item.timestamp ? (
            <time className="text-xs text-muted-foreground">{item.timestamp}</time>
          ) : null}
        </li>
      ))}
    </ol>
  );
}
