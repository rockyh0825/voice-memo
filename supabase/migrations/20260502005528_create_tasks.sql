create table tasks (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  parent_id   uuid references tasks(id) on delete cascade,
  title       text not null,
  body        text,
  status      text not null default 'draft'
              check (status in ('draft', 'todo', 'done')),
  priority    integer not null default 3
              check (priority between 1 and 4),
  due_date    date,
  source      text not null default 'manual'
              check (source in ('voice', 'manual')),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

alter table tasks enable row level security;

create policy "users manage own tasks" on tasks
  for all using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create or replace function update_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger tasks_updated_at
  before update on tasks
  for each row execute function update_updated_at();
