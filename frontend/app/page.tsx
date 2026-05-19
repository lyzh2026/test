import { redirect } from 'next/navigation';
import { cookies } from 'next/headers';

export default function RootPage() {
  const c = cookies().get('shixun_session');
  if (!c) redirect('/login');
  redirect('/tasks/new');
}
